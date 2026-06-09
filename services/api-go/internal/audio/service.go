package audio

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const DefaultTTSCacheTTL = 7 * 24 * time.Hour

type Service struct {
	store         Store
	objects       ObjectStore
	bucket        string
	maxBytes      int64
	maxDurationMS int
	allowedMIME   map[string]string
	ttsProvider   TTSProvider
	now           func() time.Time
}

type ServiceConfig struct {
	Bucket        string
	MaxBytes      int64
	MaxDurationMS int
	TTSProvider   TTSProvider
	Now           func() time.Time
}

func NewService(store Store, objects ObjectStore, cfg ServiceConfig) Service {
	if cfg.MaxBytes == 0 {
		cfg.MaxBytes = DefaultMaxUploadBytes
	}
	if cfg.MaxDurationMS == 0 {
		cfg.MaxDurationMS = DefaultMaxDurationMS
	}
	if cfg.Now == nil {
		cfg.Now = time.Now
	}
	return Service{
		store:         store,
		objects:       objects,
		bucket:        cfg.Bucket,
		maxBytes:      cfg.MaxBytes,
		maxDurationMS: cfg.MaxDurationMS,
		ttsProvider:   cfg.TTSProvider,
		allowedMIME: map[string]string{
			"audio/webm":  ".webm",
			"audio/wav":   ".wav",
			"audio/x-wav": ".wav",
			"audio/mpeg":  ".mp3",
			"audio/mp4":   ".m4a",
			"audio/ogg":   ".ogg",
		},
		now: cfg.Now,
	}
}

func (s Service) Upload(ctx context.Context, input UploadInput) (UploadResult, error) {
	input = s.normalizeUploadInput(input)
	if err := s.validateUploadInput(input); err != nil {
		return UploadResult{}, err
	}
	if input.Kind == KindUserRecording {
		accepted, err := s.store.HasAcceptedConsent(ctx, input.UserID, "recording")
		if err != nil {
			return UploadResult{}, err
		}
		if !accepted {
			return UploadResult{}, ErrConsentRequired
		}
	}

	if _, err := input.Content.Seek(0, io.SeekStart); err != nil {
		return UploadResult{}, fmt.Errorf("%w: %v", ErrInvalidInput, err)
	}

	if err := s.store.EnsureTurnForUser(ctx, input.UserID, input.SessionID, input.TurnID); err != nil {
		return UploadResult{}, err
	}

	key, err := s.objectKey(input)
	if err != nil {
		return UploadResult{}, err
	}

	if err := s.objects.EnsureBucket(ctx, s.bucket); err != nil {
		return UploadResult{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
	}

	hasher := sha256.New()
	reader := io.TeeReader(input.Content, hasher)
	if err := s.objects.PutObject(ctx, s.bucket, key, reader, input.SizeBytes, input.MimeType); err != nil {
		return UploadResult{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
	}

	checksum := hex.EncodeToString(hasher.Sum(nil))
	asset, err := s.store.CreateAsset(ctx, CreateAssetInput{
		UserID:         input.UserID,
		SessionID:      input.SessionID,
		TurnID:         input.TurnID,
		Kind:           input.Kind,
		StorageBucket:  s.bucket,
		StorageKey:     key,
		MimeType:       input.MimeType,
		SizeBytes:      input.SizeBytes,
		DurationMS:     input.DurationMS,
		ChecksumSHA256: checksum,
	})
	if err != nil {
		return UploadResult{}, err
	}

	return UploadResult{AudioAsset: asset}, nil
}

func (s Service) SynthesizeTTS(ctx context.Context, input SynthesizeTTSInput) (SynthesizeTTSResult, error) {
	input = normalizeTTSInput(input)
	if err := s.validateTTSInput(input); err != nil {
		return SynthesizeTTSResult{}, err
	}
	if isVoiceCloneVoiceID(input.VoiceID) {
		enabled, err := s.store.VoiceCloneEnabled(ctx)
		if err != nil {
			return SynthesizeTTSResult{}, err
		}
		if !enabled {
			return SynthesizeTTSResult{}, ErrVoiceCloneDisabled
		}
	}
	cacheDescriptor, err := ttsCacheDescriptor(input)
	if err != nil {
		return SynthesizeTTSResult{}, err
	}
	cacheHit := false
	tts, err := s.ttsFromCache(ctx, cacheDescriptor)
	if err == nil {
		cacheHit = true
	} else if errors.Is(err, ErrNotFound) {
		tts, err = s.ttsFromProvider(ctx, input)
		if err != nil {
			return SynthesizeTTSResult{}, err
		}
		if _, err := s.store.SaveTTSCache(ctx, SaveTTSCacheInput{
			CacheKey:     cacheDescriptor.CacheKey,
			TextHash:     cacheDescriptor.TextHash,
			VoiceID:      cacheDescriptor.VoiceID,
			SpeakingRate: cacheDescriptor.SpeakingRate,
			Emotion:      cacheDescriptor.Emotion,
			Style:        cacheDescriptor.Style,
			Provider:     tts.Provider,
			Model:        tts.Model,
			MimeType:     tts.MimeType,
			AudioBase64:  tts.AudioBase64,
			DurationMS:   positiveDuration(tts.DurationMS, 1000),
			Metadata:     tts.Metadata,
			ExpiresAt:    s.now().UTC().Add(DefaultTTSCacheTTL),
		}); err != nil {
			return SynthesizeTTSResult{}, err
		}
	} else {
		return SynthesizeTTSResult{}, err
	}

	audioBytes, err := base64.StdEncoding.DecodeString(tts.AudioBase64)
	if err != nil {
		return SynthesizeTTSResult{}, fmt.Errorf("%w: invalid tts audio", ErrStorageUnavailable)
	}
	durationMS := positiveDuration(tts.DurationMS, 1000)

	upload, err := s.Upload(ctx, UploadInput{
		UserID:     input.UserID,
		SessionID:  input.SessionID,
		TurnID:     input.TurnID,
		Kind:       KindExaminerTTS,
		FileName:   "examiner-tts" + s.extensionForMIME(tts.MimeType),
		MimeType:   tts.MimeType,
		SizeBytes:  int64(len(audioBytes)),
		DurationMS: &durationMS,
		Content:    newReadSeekNopCloser(audioBytes),
	})
	if err != nil {
		return SynthesizeTTSResult{}, err
	}

	return SynthesizeTTSResult{
		AudioAsset: upload.AudioAsset,
		TTS: TTSResultBrief{
			Provider:   tts.Provider,
			Model:      tts.Model,
			VoiceID:    tts.VoiceID,
			MimeType:   tts.MimeType,
			DurationMS: durationMS,
			CacheHit:   cacheHit,
			CacheKey:   cacheDescriptor.CacheKey,
			Metadata:   tts.Metadata,
		},
	}, nil
}

func (s Service) CleanupExpiredTTSCache(ctx context.Context) (CleanupTTSCacheResult, error) {
	deleted, err := s.store.CleanupExpiredTTSCache(ctx, s.now().UTC())
	if err != nil {
		return CleanupTTSCacheResult{}, err
	}
	return CleanupTTSCacheResult{DeletedCount: deleted}, nil
}

func (s Service) SignedURL(ctx context.Context, userID string, assetID string, expiresSeconds int) (SignedURLResult, error) {
	if expiresSeconds <= 0 {
		expiresSeconds = DefaultSignedURLSeconds
	}
	if expiresSeconds > MaxSignedURLSeconds {
		expiresSeconds = MaxSignedURLSeconds
	}

	asset, err := s.store.GetAssetForUser(ctx, userID, assetID)
	if err != nil {
		return SignedURLResult{}, err
	}

	expires := time.Duration(expiresSeconds) * time.Second
	signed, err := s.objects.PresignedGetObject(ctx, asset.StorageBucket, asset.StorageKey, expires)
	if err != nil {
		return SignedURLResult{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
	}

	return SignedURLResult{
		AudioAsset: asset,
		SignedURL:  signed,
		ExpiresAt:  s.now().UTC().Add(expires),
	}, nil
}

func (s Service) normalizeUploadInput(input UploadInput) UploadInput {
	input.Kind = strings.TrimSpace(input.Kind)
	input.MimeType = strings.ToLower(strings.TrimSpace(strings.Split(input.MimeType, ";")[0]))
	if input.MimeType == "" || input.MimeType == "application/octet-stream" {
		if inferred := mimeTypeFromExtension(filepath.Ext(input.FileName)); inferred != "" {
			input.MimeType = inferred
		}
	}
	if input.Kind == "" {
		input.Kind = KindUserRecording
	}
	return input
}

func (s Service) validateUploadInput(input UploadInput) error {
	if input.UserID == "" || input.SessionID == "" || input.TurnID == "" {
		return fmt.Errorf("%w: session_id and turn_id are required", ErrInvalidInput)
	}
	if input.Content == nil {
		return fmt.Errorf("%w: file is required", ErrInvalidInput)
	}
	if input.SizeBytes <= 0 {
		return fmt.Errorf("%w: file cannot be empty", ErrInvalidInput)
	}
	if input.SizeBytes > s.maxBytes {
		return ErrFileTooLarge
	}
	if input.DurationMS == nil || *input.DurationMS <= 0 {
		return fmt.Errorf("%w: duration_ms is required", ErrInvalidInput)
	}
	if *input.DurationMS > s.maxDurationMS {
		return ErrDurationTooLong
	}
	if _, ok := s.allowedMIME[input.MimeType]; !ok {
		return ErrUnsupportedType
	}
	if input.Kind != KindUserRecording && input.Kind != KindExaminerTTS && input.Kind != KindReference {
		return ErrInvalidInput
	}
	return nil
}

func normalizeTTSInput(input SynthesizeTTSInput) SynthesizeTTSInput {
	input.SessionID = strings.TrimSpace(input.SessionID)
	input.TurnID = strings.TrimSpace(input.TurnID)
	input.Text = strings.TrimSpace(input.Text)
	input.VoiceID = strings.TrimSpace(input.VoiceID)
	if input.VoiceID == "" {
		input.VoiceID = "ielts_examiner_default"
	}
	if input.SpeakingRate == nil {
		rate := 1.0
		input.SpeakingRate = &rate
	}
	if input.Emotion == nil || strings.TrimSpace(*input.Emotion) == "" {
		emotion := "neutral"
		input.Emotion = &emotion
	}
	if input.Style == nil || strings.TrimSpace(*input.Style) == "" {
		style := "examiner"
		input.Style = &style
	}
	return input
}

func isVoiceCloneVoiceID(voiceID string) bool {
	normalized := strings.ToLower(strings.TrimSpace(voiceID))
	return strings.HasPrefix(normalized, "voiceclone:") ||
		strings.HasPrefix(normalized, "clone:") ||
		strings.Contains(normalized, "voiceclone")
}

func (s Service) validateTTSInput(input SynthesizeTTSInput) error {
	if input.UserID == "" || input.SessionID == "" || input.TurnID == "" {
		return fmt.Errorf("%w: session_id and turn_id are required", ErrInvalidInput)
	}
	if input.Text == "" || len(input.Text) > 1200 {
		return ErrInvalidInput
	}
	if input.SpeakingRate != nil && (*input.SpeakingRate < 0.5 || *input.SpeakingRate > 1.5) {
		return ErrInvalidInput
	}
	return nil
}

func (s Service) extensionForMIME(mimeType string) string {
	if extension, ok := s.allowedMIME[strings.ToLower(strings.TrimSpace(mimeType))]; ok {
		return extension
	}
	return ".wav"
}

func (s Service) ttsFromCache(ctx context.Context, descriptor TTSCacheDescriptor) (TTSProviderResponse, error) {
	entry, err := s.store.GetTTSCache(ctx, descriptor.CacheKey, s.now().UTC())
	if err != nil {
		return TTSProviderResponse{}, err
	}
	durationMS := entry.DurationMS
	return TTSProviderResponse{
		Text:        descriptor.Text,
		AudioBase64: entry.AudioBase64,
		MimeType:    entry.MimeType,
		Provider:    entry.Provider,
		Model:       entry.Model,
		VoiceID:     entry.VoiceID,
		DurationMS:  &durationMS,
		Metadata:    entry.Metadata,
	}, nil
}

func (s Service) ttsFromProvider(ctx context.Context, input SynthesizeTTSInput) (TTSProviderResponse, error) {
	if s.ttsProvider == nil {
		return TTSProviderResponse{}, fmt.Errorf("%w: tts provider is not configured", ErrStorageUnavailable)
	}
	tts, err := s.ttsProvider.Synthesize(ctx, TTSProviderRequest{
		Text:         input.Text,
		VoiceID:      input.VoiceID,
		SpeakingRate: input.SpeakingRate,
		Emotion:      input.Emotion,
		Style:        input.Style,
	})
	if err != nil {
		return TTSProviderResponse{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
	}
	return tts, nil
}

type TTSCacheDescriptor struct {
	CacheKey     string
	Text         string
	TextHash     string
	VoiceID      string
	SpeakingRate float64
	Emotion      string
	Style        string
}

func ttsCacheDescriptor(input SynthesizeTTSInput) (TTSCacheDescriptor, error) {
	rate := 1.0
	if input.SpeakingRate != nil {
		rate = *input.SpeakingRate
	}
	emotion := "neutral"
	if input.Emotion != nil {
		emotion = strings.TrimSpace(*input.Emotion)
	}
	style := "examiner"
	if input.Style != nil {
		style = strings.TrimSpace(*input.Style)
	}
	textHash := sha256Hex(input.Text)
	payload := map[string]any{
		"text_hash":     textHash,
		"voice_id":      input.VoiceID,
		"speaking_rate": rate,
		"emotion":       emotion,
		"style":         style,
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return TTSCacheDescriptor{}, err
	}
	return TTSCacheDescriptor{
		CacheKey:     sha256Hex(string(encoded)),
		Text:         input.Text,
		TextHash:     textHash,
		VoiceID:      input.VoiceID,
		SpeakingRate: rate,
		Emotion:      emotion,
		Style:        style,
	}, nil
}

func sha256Hex(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func positiveDuration(value *int, fallback int) int {
	if value != nil && *value > 0 {
		return *value
	}
	return fallback
}

func (s Service) objectKey(input UploadInput) (string, error) {
	token, err := randomHex(12)
	if err != nil {
		return "", err
	}
	extension := strings.ToLower(filepath.Ext(input.FileName))
	if extension == "" || len(extension) > 8 {
		extension = s.allowedMIME[input.MimeType]
	}
	name := sanitizeFilename(strings.TrimSuffix(filepath.Base(input.FileName), filepath.Ext(input.FileName)))
	if name == "" {
		name = "audio"
	}
	return fmt.Sprintf("sessions/%s/turns/%s/%s-%s%s", input.SessionID, input.TurnID, token, name, extension), nil
}

type readSeekNopCloser struct {
	*bytes.Reader
}

func newReadSeekNopCloser(value []byte) readSeekNopCloser {
	return readSeekNopCloser{Reader: bytes.NewReader(value)}
}

func (readSeekNopCloser) Close() error {
	return nil
}

func randomHex(bytes int) (string, error) {
	buffer := make([]byte, bytes)
	if _, err := rand.Read(buffer); err != nil {
		return "", err
	}
	return hex.EncodeToString(buffer), nil
}

var filenamePattern = regexp.MustCompile(`[^a-zA-Z0-9._-]+`)

func sanitizeFilename(value string) string {
	value = filenamePattern.ReplaceAllString(value, "-")
	value = strings.Trim(value, ".-_")
	if len(value) > 80 {
		value = value[:80]
	}
	return value
}

func mimeTypeFromExtension(extension string) string {
	switch strings.ToLower(extension) {
	case ".webm":
		return "audio/webm"
	case ".wav":
		return "audio/wav"
	case ".mp3":
		return "audio/mpeg"
	case ".m4a":
		return "audio/mp4"
	case ".ogg":
		return "audio/ogg"
	default:
		return ""
	}
}
