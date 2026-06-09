package audio

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"io"
	"testing"
	"time"
)

func TestServiceUploadStoresObjectAfterOwnershipCheck(t *testing.T) {
	payload := []byte("fake-webm-audio")
	durationMS := 18000
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	service := NewService(store, objects, ServiceConfig{
		Bucket:        "ielts-speaking-test",
		MaxBytes:      1024,
		MaxDurationMS: 60000,
	})

	result, err := service.Upload(context.Background(), UploadInput{
		UserID:     "user_001",
		SessionID:  "session_001",
		TurnID:     "turn_001",
		FileName:   "answer.webm",
		MimeType:   "audio/webm",
		SizeBytes:  int64(len(payload)),
		DurationMS: &durationMS,
		Content:    newReadSeekCloser(payload),
	})
	if err != nil {
		t.Fatalf("Upload() error = %v", err)
	}

	if store.ensureCalls != 1 {
		t.Fatalf("ensureCalls = %d, want 1", store.ensureCalls)
	}
	if objects.putCalls != 1 {
		t.Fatalf("putCalls = %d, want 1", objects.putCalls)
	}
	if store.createCalls != 1 {
		t.Fatalf("createCalls = %d, want 1", store.createCalls)
	}
	if objects.putBucket != "ielts-speaking-test" {
		t.Fatalf("putBucket = %q", objects.putBucket)
	}
	if objects.putContentType != "audio/webm" {
		t.Fatalf("putContentType = %q", objects.putContentType)
	}
	if !bytes.Equal(objects.putData, payload) {
		t.Fatalf("uploaded payload = %q, want %q", objects.putData, payload)
	}

	sum := sha256.Sum256(payload)
	wantChecksum := hex.EncodeToString(sum[:])
	if store.created.ChecksumSHA256 != wantChecksum {
		t.Fatalf("checksum = %q, want %q", store.created.ChecksumSHA256, wantChecksum)
	}
	if result.AudioAsset.ID == "" {
		t.Fatal("Upload() returned empty audio asset id")
	}
}

func TestServiceUploadInfersMimeFromKnownExtension(t *testing.T) {
	payload := []byte("fake-webm-audio")
	durationMS := 18000
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	service := NewService(store, objects, ServiceConfig{Bucket: "ielts-speaking-test"})

	_, err := service.Upload(context.Background(), UploadInput{
		UserID:     "user_001",
		SessionID:  "session_001",
		TurnID:     "turn_001",
		FileName:   "answer.webm",
		MimeType:   "application/octet-stream",
		SizeBytes:  int64(len(payload)),
		DurationMS: &durationMS,
		Content:    newReadSeekCloser(payload),
	})
	if err != nil {
		t.Fatalf("Upload() error = %v", err)
	}
	if objects.putContentType != "audio/webm" {
		t.Fatalf("putContentType = %q, want audio/webm", objects.putContentType)
	}
}

func TestServiceUploadRejectsInvalidFiles(t *testing.T) {
	durationMS := 5000
	longDurationMS := 18000
	payload := []byte("fake-webm-audio")

	cases := []struct {
		name    string
		input   UploadInput
		maxByte int64
		wantErr error
	}{
		{
			name: "too large",
			input: UploadInput{
				UserID: "user_001", SessionID: "session_001", TurnID: "turn_001",
				FileName: "answer.webm", MimeType: "audio/webm", SizeBytes: 2048, DurationMS: &durationMS, Content: newReadSeekCloser(payload),
			},
			maxByte: 1024,
			wantErr: ErrFileTooLarge,
		},
		{
			name: "unsupported mime",
			input: UploadInput{
				UserID: "user_001", SessionID: "session_001", TurnID: "turn_001",
				FileName: "answer.txt", MimeType: "text/plain", SizeBytes: int64(len(payload)), DurationMS: &durationMS, Content: newReadSeekCloser(payload),
			},
			maxByte: 1024,
			wantErr: ErrUnsupportedType,
		},
		{
			name: "missing duration",
			input: UploadInput{
				UserID: "user_001", SessionID: "session_001", TurnID: "turn_001",
				FileName: "answer.webm", MimeType: "audio/webm", SizeBytes: int64(len(payload)), Content: newReadSeekCloser(payload),
			},
			maxByte: 1024,
			wantErr: ErrInvalidInput,
		},
		{
			name: "duration too long",
			input: UploadInput{
				UserID: "user_001", SessionID: "session_001", TurnID: "turn_001",
				FileName: "answer.webm", MimeType: "audio/webm", SizeBytes: int64(len(payload)), DurationMS: &longDurationMS, Content: newReadSeekCloser(payload),
			},
			maxByte: 1024,
			wantErr: ErrDurationTooLong,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			store := &fakeStore{}
			objects := &fakeObjectStore{}
			service := NewService(store, objects, ServiceConfig{
				Bucket:        "ielts-speaking-test",
				MaxBytes:      tc.maxByte,
				MaxDurationMS: 10000,
			})

			_, err := service.Upload(context.Background(), tc.input)
			if !errors.Is(err, tc.wantErr) {
				t.Fatalf("Upload() error = %v, want %v", err, tc.wantErr)
			}
			if objects.putCalls != 0 {
				t.Fatalf("putCalls = %d, want 0", objects.putCalls)
			}
		})
	}
}

func TestServiceUploadChecksTurnBeforeObjectPut(t *testing.T) {
	durationMS := 18000
	store := &fakeStore{ensureErr: ErrNotFound}
	objects := &fakeObjectStore{}
	service := NewService(store, objects, ServiceConfig{Bucket: "ielts-speaking-test"})

	_, err := service.Upload(context.Background(), UploadInput{
		UserID:     "user_001",
		SessionID:  "session_001",
		TurnID:     "turn_001",
		FileName:   "answer.webm",
		MimeType:   "audio/webm",
		SizeBytes:  16,
		DurationMS: &durationMS,
		Content:    newReadSeekCloser([]byte("fake-webm-audio")),
	})
	if !errors.Is(err, ErrNotFound) {
		t.Fatalf("Upload() error = %v, want %v", err, ErrNotFound)
	}
	if objects.putCalls != 0 {
		t.Fatalf("putCalls = %d, want 0", objects.putCalls)
	}
	if store.createCalls != 0 {
		t.Fatalf("createCalls = %d, want 0", store.createCalls)
	}
}

func TestServiceUploadRequiresRecordingConsent(t *testing.T) {
	durationMS := 18000
	accepted := false
	store := &fakeStore{consentAccepted: &accepted}
	objects := &fakeObjectStore{}
	service := NewService(store, objects, ServiceConfig{Bucket: "ielts-speaking-test"})

	_, err := service.Upload(context.Background(), UploadInput{
		UserID:     "user_001",
		SessionID:  "session_001",
		TurnID:     "turn_001",
		FileName:   "answer.webm",
		MimeType:   "audio/webm",
		SizeBytes:  16,
		DurationMS: &durationMS,
		Content:    newReadSeekCloser([]byte("fake-webm-audio")),
	})
	if !errors.Is(err, ErrConsentRequired) {
		t.Fatalf("Upload() error = %v, want %v", err, ErrConsentRequired)
	}
	if objects.putCalls != 0 {
		t.Fatalf("putCalls = %d, want 0", objects.putCalls)
	}
}

func TestServiceSynthesizeTTSStoresExaminerAudio(t *testing.T) {
	durationMS := 1200
	payload := []byte("fake-wav-audio")
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	tts := &fakeTTSProvider{
		response: TTSProviderResponse{
			Text:        "Let's talk about your hometown.",
			AudioBase64: base64.StdEncoding.EncodeToString(payload),
			MimeType:    "audio/wav",
			Provider:    "mock_tts",
			Model:       "mimo-v2.5-tts",
			VoiceID:     "examiner_voice_a",
			DurationMS:  &durationMS,
			Metadata:    map[string]any{"style": "examiner"},
		},
	}
	service := NewService(store, objects, ServiceConfig{
		Bucket:      "ielts-speaking-test",
		TTSProvider: tts,
	})
	rate := 1.1

	result, err := service.SynthesizeTTS(context.Background(), SynthesizeTTSInput{
		UserID:       "user_001",
		SessionID:    "session_001",
		TurnID:       "turn_001",
		Text:         "Let's talk about your hometown.",
		VoiceID:      "examiner_voice_a",
		SpeakingRate: &rate,
	})
	if err != nil {
		t.Fatalf("SynthesizeTTS() error = %v", err)
	}

	if len(tts.calls) != 1 {
		t.Fatalf("tts calls = %d, want 1", len(tts.calls))
	}
	if tts.calls[0].VoiceID != "examiner_voice_a" || tts.calls[0].SpeakingRate == nil || *tts.calls[0].SpeakingRate != rate {
		t.Fatalf("unexpected tts request = %+v", tts.calls[0])
	}
	if store.created.Kind != KindExaminerTTS {
		t.Fatalf("asset kind = %q, want %q", store.created.Kind, KindExaminerTTS)
	}
	if store.created.MimeType != "audio/wav" {
		t.Fatalf("mime = %q, want audio/wav", store.created.MimeType)
	}
	if !bytes.Equal(objects.putData, payload) {
		t.Fatalf("stored payload = %q, want %q", objects.putData, payload)
	}
	if result.TTS.Provider != "mock_tts" || result.TTS.Model != "mimo-v2.5-tts" {
		t.Fatalf("tts brief = %+v", result.TTS)
	}
	if result.TTS.CacheHit {
		t.Fatal("first synthesis should not be a cache hit")
	}
	if result.TTS.CacheKey == "" {
		t.Fatal("cache key should be returned")
	}
	if store.saveCacheCalls != 1 {
		t.Fatalf("saveCacheCalls = %d, want 1", store.saveCacheCalls)
	}
}

func TestServiceSynthesizeTTSBlocksVoiceCloneWhenDisabled(t *testing.T) {
	store := &fakeStore{voiceCloneEnabled: false}
	objects := &fakeObjectStore{}
	tts := &fakeTTSProvider{}
	service := NewService(store, objects, ServiceConfig{
		Bucket:      "ielts-speaking-test",
		TTSProvider: tts,
	})

	_, err := service.SynthesizeTTS(context.Background(), SynthesizeTTSInput{
		UserID:    "user_001",
		SessionID: "session_001",
		TurnID:    "turn_001",
		Text:      "Let's talk about your hometown.",
		VoiceID:   "voiceclone:unreviewed-speaker",
	})
	if !errors.Is(err, ErrVoiceCloneDisabled) {
		t.Fatalf("SynthesizeTTS() error = %v, want %v", err, ErrVoiceCloneDisabled)
	}
	if len(tts.calls) != 0 {
		t.Fatalf("tts calls = %d, want 0", len(tts.calls))
	}
}

func TestServiceSynthesizeTTSUsesCacheWithoutCallingProviderAgain(t *testing.T) {
	durationMS := 1200
	payload := []byte("fake-wav-audio")
	store := &fakeStore{}
	objects := &fakeObjectStore{}
	tts := &fakeTTSProvider{
		response: TTSProviderResponse{
			Text:        "Let's talk about your hometown.",
			AudioBase64: base64.StdEncoding.EncodeToString(payload),
			MimeType:    "audio/wav",
			Provider:    "mock_tts",
			Model:       "mimo-v2.5-tts",
			VoiceID:     "examiner_voice_a",
			DurationMS:  &durationMS,
			Metadata:    map[string]any{"style": "examiner"},
		},
	}
	service := NewService(store, objects, ServiceConfig{
		Bucket:      "ielts-speaking-test",
		TTSProvider: tts,
	})
	input := SynthesizeTTSInput{
		UserID:    "user_001",
		SessionID: "session_001",
		TurnID:    "turn_001",
		Text:      "Let's talk about your hometown.",
		VoiceID:   "examiner_voice_a",
	}

	first, err := service.SynthesizeTTS(context.Background(), input)
	if err != nil {
		t.Fatalf("first SynthesizeTTS() error = %v", err)
	}
	input.TurnID = "turn_002"
	second, err := service.SynthesizeTTS(context.Background(), input)
	if err != nil {
		t.Fatalf("second SynthesizeTTS() error = %v", err)
	}

	if len(tts.calls) != 1 {
		t.Fatalf("tts calls = %d, want 1", len(tts.calls))
	}
	if first.TTS.CacheHit {
		t.Fatal("first call should be cache miss")
	}
	if !second.TTS.CacheHit {
		t.Fatal("second call should be cache hit")
	}
	if first.TTS.CacheKey != second.TTS.CacheKey {
		t.Fatalf("cache keys differ: %s vs %s", first.TTS.CacheKey, second.TTS.CacheKey)
	}
	if objects.putCalls != 2 {
		t.Fatalf("putCalls = %d, want 2 new turn assets", objects.putCalls)
	}
}

func TestServiceCleanupExpiredTTSCache(t *testing.T) {
	store := &fakeStore{cleanupDeleted: 3}
	service := NewService(store, &fakeObjectStore{}, ServiceConfig{Bucket: "ielts-speaking-test"})

	result, err := service.CleanupExpiredTTSCache(context.Background())
	if err != nil {
		t.Fatalf("CleanupExpiredTTSCache() error = %v", err)
	}
	if result.DeletedCount != 3 {
		t.Fatalf("DeletedCount = %d, want 3", result.DeletedCount)
	}
	if store.cleanupCalls != 1 {
		t.Fatalf("cleanupCalls = %d, want 1", store.cleanupCalls)
	}
}

func TestServiceSignedURLCapsExpires(t *testing.T) {
	now := time.Date(2026, 6, 7, 10, 0, 0, 0, time.UTC)
	store := &fakeStore{
		getAsset: Asset{
			ID:            "audio_001",
			StorageBucket: "ielts-speaking-test",
			StorageKey:    "sessions/session_001/turns/turn_001/audio.webm",
		},
	}
	objects := &fakeObjectStore{}
	service := NewService(store, objects, ServiceConfig{
		Bucket: "ielts-speaking-test",
		Now:    func() time.Time { return now },
	})

	result, err := service.SignedURL(context.Background(), "user_001", "audio_001", MaxSignedURLSeconds+999)
	if err != nil {
		t.Fatalf("SignedURL() error = %v", err)
	}
	if objects.presignExpires != time.Hour {
		t.Fatalf("presign expires = %s, want 1h", objects.presignExpires)
	}
	if !result.ExpiresAt.Equal(now.Add(time.Hour)) {
		t.Fatalf("ExpiresAt = %s, want %s", result.ExpiresAt, now.Add(time.Hour))
	}
	if result.SignedURL == "" {
		t.Fatal("SignedURL() returned empty url")
	}
}

type readSeekCloser struct {
	*bytes.Reader
}

func newReadSeekCloser(payload []byte) readSeekCloser {
	return readSeekCloser{Reader: bytes.NewReader(payload)}
}

func (r readSeekCloser) Close() error {
	return nil
}

type fakeStore struct {
	ensureErr         error
	createErr         error
	getErr            error
	cacheErr          error
	consentErr        error
	voiceCloneErr     error
	ensureCalls       int
	createCalls       int
	getCalls          int
	getCacheCalls     int
	saveCacheCalls    int
	cleanupCalls      int
	cleanupDeleted    int
	created           CreateAssetInput
	getAsset          Asset
	cache             map[string]TTSCacheEntry
	lastSavedCache    SaveTTSCacheInput
	consentAccepted   *bool
	voiceCloneEnabled bool
}

func (s *fakeStore) EnsureTurnForUser(context.Context, string, string, string) error {
	s.ensureCalls++
	return s.ensureErr
}

func (s *fakeStore) HasAcceptedConsent(context.Context, string, string) (bool, error) {
	if s.consentErr != nil {
		return false, s.consentErr
	}
	if s.consentAccepted != nil {
		return *s.consentAccepted, nil
	}
	return true, nil
}

func (s *fakeStore) VoiceCloneEnabled(context.Context) (bool, error) {
	if s.voiceCloneErr != nil {
		return false, s.voiceCloneErr
	}
	return s.voiceCloneEnabled, nil
}

func (s *fakeStore) CreateAsset(_ context.Context, input CreateAssetInput) (Asset, error) {
	s.createCalls++
	s.created = input
	if s.createErr != nil {
		return Asset{}, s.createErr
	}
	durationMS := input.DurationMS
	checksum := input.ChecksumSHA256
	return Asset{
		ID:             "audio_001",
		UserID:         &input.UserID,
		SessionID:      &input.SessionID,
		TurnID:         &input.TurnID,
		Kind:           input.Kind,
		StorageBucket:  input.StorageBucket,
		StorageKey:     input.StorageKey,
		MimeType:       input.MimeType,
		SizeBytes:      input.SizeBytes,
		DurationMS:     durationMS,
		ChecksumSHA256: &checksum,
		CreatedAt:      time.Now().UTC(),
	}, nil
}

func (s *fakeStore) GetAssetForUser(context.Context, string, string) (Asset, error) {
	s.getCalls++
	if s.getErr != nil {
		return Asset{}, s.getErr
	}
	if s.getAsset.ID != "" {
		return s.getAsset, nil
	}
	return Asset{ID: "audio_001", StorageBucket: "ielts-speaking-test", StorageKey: "audio.webm"}, nil
}

func (s *fakeStore) GetTTSCache(_ context.Context, cacheKey string, now time.Time) (TTSCacheEntry, error) {
	s.getCacheCalls++
	if s.cacheErr != nil {
		return TTSCacheEntry{}, s.cacheErr
	}
	if s.cache == nil {
		return TTSCacheEntry{}, ErrNotFound
	}
	entry, ok := s.cache[cacheKey]
	if !ok || !entry.ExpiresAt.After(now) {
		return TTSCacheEntry{}, ErrNotFound
	}
	return entry, nil
}

func (s *fakeStore) SaveTTSCache(_ context.Context, input SaveTTSCacheInput) (TTSCacheEntry, error) {
	s.saveCacheCalls++
	s.lastSavedCache = input
	if s.cache == nil {
		s.cache = map[string]TTSCacheEntry{}
	}
	entry := TTSCacheEntry{
		CacheKey:     input.CacheKey,
		TextHash:     input.TextHash,
		VoiceID:      input.VoiceID,
		SpeakingRate: input.SpeakingRate,
		Emotion:      input.Emotion,
		Style:        input.Style,
		Provider:     input.Provider,
		Model:        input.Model,
		MimeType:     input.MimeType,
		AudioBase64:  input.AudioBase64,
		DurationMS:   input.DurationMS,
		Metadata:     input.Metadata,
		ExpiresAt:    input.ExpiresAt,
		CreatedAt:    time.Now().UTC(),
		UpdatedAt:    time.Now().UTC(),
	}
	s.cache[input.CacheKey] = entry
	return entry, nil
}

func (s *fakeStore) CleanupExpiredTTSCache(context.Context, time.Time) (int, error) {
	s.cleanupCalls++
	return s.cleanupDeleted, nil
}

type fakeObjectStore struct {
	ensureErr      error
	putErr         error
	presignErr     error
	ensureCalls    int
	putCalls       int
	presignCalls   int
	putBucket      string
	putKey         string
	putContentType string
	putSize        int64
	putData        []byte
	presignExpires time.Duration
}

func (s *fakeObjectStore) EnsureBucket(context.Context, string) error {
	s.ensureCalls++
	return s.ensureErr
}

func (s *fakeObjectStore) PutObject(_ context.Context, bucket string, key string, content io.Reader, size int64, contentType string) error {
	s.putCalls++
	s.putBucket = bucket
	s.putKey = key
	s.putSize = size
	s.putContentType = contentType
	data, err := io.ReadAll(content)
	if err != nil {
		return err
	}
	s.putData = data
	return s.putErr
}

func (s *fakeObjectStore) PresignedGetObject(_ context.Context, bucket string, key string, expires time.Duration) (string, error) {
	s.presignCalls++
	s.presignExpires = expires
	if s.presignErr != nil {
		return "", s.presignErr
	}
	return "http://storage.local/" + bucket + "/" + key, nil
}

type fakeTTSProvider struct {
	response TTSProviderResponse
	err      error
	calls    []TTSProviderRequest
}

func (s *fakeTTSProvider) Synthesize(_ context.Context, request TTSProviderRequest) (TTSProviderResponse, error) {
	s.calls = append(s.calls, request)
	if s.err != nil {
		return TTSProviderResponse{}, s.err
	}
	return s.response, nil
}
