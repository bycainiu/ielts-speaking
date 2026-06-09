package audio

import "time"

const (
	KindUserRecording = "user_recording"
	KindExaminerTTS   = "examiner_tts"
	KindReference     = "reference"

	DefaultSignedURLSeconds = 15 * 60
	MaxSignedURLSeconds     = 60 * 60
	DefaultMaxUploadBytes   = 25 * 1024 * 1024
	DefaultMaxDurationMS    = 10 * 60 * 1000
)

type Asset struct {
	ID             string     `json:"id"`
	UserID         *string    `json:"user_id,omitempty"`
	SessionID      *string    `json:"session_id,omitempty"`
	TurnID         *string    `json:"turn_id,omitempty"`
	Kind           string     `json:"kind"`
	StorageBucket  string     `json:"storage_bucket"`
	StorageKey     string     `json:"storage_key"`
	MimeType       string     `json:"mime_type"`
	SizeBytes      int64      `json:"size_bytes"`
	DurationMS     *int       `json:"duration_ms,omitempty"`
	ChecksumSHA256 *string    `json:"checksum_sha256,omitempty"`
	CreatedAt      time.Time  `json:"created_at"`
	DeletedAt      *time.Time `json:"deleted_at,omitempty"`
}

type CreateAssetInput struct {
	UserID         string
	SessionID      string
	TurnID         string
	Kind           string
	StorageBucket  string
	StorageKey     string
	MimeType       string
	SizeBytes      int64
	DurationMS     *int
	ChecksumSHA256 string
}

type UploadInput struct {
	UserID     string
	SessionID  string
	TurnID     string
	Kind       string
	FileName   string
	MimeType   string
	SizeBytes  int64
	DurationMS *int
	Content    ReadSeekCloser
}

type SynthesizeTTSInput struct {
	UserID       string   `json:"-"`
	SessionID    string   `json:"session_id" binding:"required"`
	TurnID       string   `json:"turn_id" binding:"required"`
	Text         string   `json:"text" binding:"required,min=1,max=1200"`
	VoiceID      string   `json:"voice_id" binding:"omitempty,max=120"`
	SpeakingRate *float64 `json:"speaking_rate" binding:"omitempty,min=0.5,max=1.5"`
	Emotion      *string  `json:"emotion" binding:"omitempty,max=60"`
	Style        *string  `json:"style" binding:"omitempty,max=80"`
}

type TTSCacheEntry struct {
	CacheKey     string         `json:"cache_key"`
	TextHash     string         `json:"text_hash"`
	VoiceID      string         `json:"voice_id"`
	SpeakingRate float64        `json:"speaking_rate"`
	Emotion      string         `json:"emotion"`
	Style        string         `json:"style"`
	Provider     string         `json:"provider"`
	Model        string         `json:"model"`
	MimeType     string         `json:"mime_type"`
	AudioBase64  string         `json:"audio_base64"`
	DurationMS   int            `json:"duration_ms"`
	Metadata     map[string]any `json:"metadata"`
	ExpiresAt    time.Time      `json:"expires_at"`
	CreatedAt    time.Time      `json:"created_at"`
	UpdatedAt    time.Time      `json:"updated_at"`
}

type SaveTTSCacheInput struct {
	CacheKey     string
	TextHash     string
	VoiceID      string
	SpeakingRate float64
	Emotion      string
	Style        string
	Provider     string
	Model        string
	MimeType     string
	AudioBase64  string
	DurationMS   int
	Metadata     map[string]any
	ExpiresAt    time.Time
}

type CleanupTTSCacheResult struct {
	DeletedCount int `json:"deleted_count"`
}

type UploadResult struct {
	AudioAsset Asset `json:"audio_asset"`
}

type SynthesizeTTSResult struct {
	AudioAsset Asset          `json:"audio_asset"`
	TTS        TTSResultBrief `json:"tts"`
}

type TTSResultBrief struct {
	Provider   string         `json:"provider"`
	Model      string         `json:"model"`
	VoiceID    string         `json:"voice_id"`
	MimeType   string         `json:"mime_type"`
	DurationMS int            `json:"duration_ms"`
	CacheHit   bool           `json:"cache_hit"`
	CacheKey   string         `json:"cache_key"`
	Metadata   map[string]any `json:"metadata"`
}

type TTSProviderRequest struct {
	Text         string   `json:"text"`
	VoiceID      string   `json:"voice_id,omitempty"`
	SpeakingRate *float64 `json:"speaking_rate,omitempty"`
	Emotion      *string  `json:"emotion,omitempty"`
	Style        *string  `json:"style,omitempty"`
}

type TTSProviderResponse struct {
	Text        string         `json:"text"`
	AudioBase64 string         `json:"audio_base64"`
	MimeType    string         `json:"mime_type"`
	Provider    string         `json:"provider"`
	Model       string         `json:"model"`
	VoiceID     string         `json:"voice_id"`
	DurationMS  *int           `json:"duration_ms"`
	Metadata    map[string]any `json:"metadata"`
}

type SignedURLResult struct {
	AudioAsset Asset     `json:"audio_asset"`
	SignedURL  string    `json:"signed_url"`
	ExpiresAt  time.Time `json:"expires_at"`
}

type ReadSeekCloser interface {
	Read(p []byte) (int, error)
	Seek(offset int64, whence int) (int64, error)
	Close() error
}
