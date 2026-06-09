package session

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/ielts-speaking/platform/services/api-go/internal/auth"
)

func TestPlannedParts(t *testing.T) {
	part := 2
	topicID := "topic_001"

	cases := []struct {
		name  string
		input CreateSessionInput
		want  []int
	}{
		{name: "full exam", input: CreateSessionInput{Mode: ModeFullExam}, want: []int{1, 2, 3}},
		{name: "part practice", input: CreateSessionInput{Mode: ModePartPractice, TargetPart: &part}, want: []int{2}},
		{name: "topic practice all parts", input: CreateSessionInput{Mode: ModeTopicPractice, TopicID: &topicID}, want: []int{1, 2, 3}},
		{name: "topic practice target part", input: CreateSessionInput{Mode: ModeTopicPractice, TopicID: &topicID, TargetPart: &part}, want: []int{2}},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := plannedParts(tc.input)
			if err != nil {
				t.Fatalf("plannedParts() error = %v", err)
			}
			if len(got) != len(tc.want) {
				t.Fatalf("parts = %v, want %v", got, tc.want)
			}
			for index := range got {
				if got[index] != tc.want[index] {
					t.Fatalf("parts = %v, want %v", got, tc.want)
				}
			}
		})
	}
}

func TestPartPracticeRequiresTargetPart(t *testing.T) {
	_, err := plannedParts(CreateSessionInput{Mode: ModePartPractice})
	if err == nil {
		t.Fatal("expected error for part_practice without target_part")
	}
}

func TestHandlerCreateStartFinishSession(t *testing.T) {
	router, token := testRouter(t)

	createResponse := performJSON(router, http.MethodPost, "/api/sessions", map[string]any{
		"mode":        ModePartPractice,
		"target_part": 1,
	}, token)
	if createResponse.Code != http.StatusCreated {
		t.Fatalf("create status = %d, body = %s", createResponse.Code, createResponse.Body.String())
	}

	startResponse := performJSON(router, http.MethodPost, "/api/sessions/session_001/start", nil, token)
	if startResponse.Code != http.StatusOK {
		t.Fatalf("start status = %d, body = %s", startResponse.Code, startResponse.Body.String())
	}

	finishResponse := performJSON(router, http.MethodPost, "/api/sessions/session_001/finish", nil, token)
	if finishResponse.Code != http.StatusOK {
		t.Fatalf("finish status = %d, body = %s", finishResponse.Code, finishResponse.Body.String())
	}
}

func TestHandlerRecordsTurnASRAudioAndMetrics(t *testing.T) {
	router, token := testRouter(t)

	turnResponse := performJSON(router, http.MethodPost, "/api/sessions/session_001/turns", map[string]any{
		"part":          1,
		"speaker":       SpeakerUser,
		"status":        TurnStatusRecording,
		"question_text": "Where is your hometown?",
		"answer_text":   "I come from Hangzhou.",
	}, token)
	if turnResponse.Code != http.StatusCreated {
		t.Fatalf("turn status = %d, body = %s", turnResponse.Code, turnResponse.Body.String())
	}

	audioResponse := performJSON(router, http.MethodPost, "/api/sessions/session_001/turns/turn_001/audio-assets", map[string]any{
		"kind":           "user_recording",
		"storage_bucket": "ielts-speaking-local",
		"storage_key":    "sessions/session_001/turn_001.webm",
		"mime_type":      "audio/webm",
		"size_bytes":     1024,
		"duration_ms":    18000,
	}, token)
	if audioResponse.Code != http.StatusCreated {
		t.Fatalf("audio status = %d, body = %s", audioResponse.Code, audioResponse.Body.String())
	}

	asrResponse := performJSON(router, http.MethodPost, "/api/sessions/session_001/turns/turn_001/asr-results", map[string]any{
		"provider":   "mock",
		"model":      "mimo-v2.5-asr",
		"transcript": "I come from Hangzhou.",
		"confidence": 0.91,
		"raw_response": map[string]any{
			"id":         "asr_provider_001",
			"api_key":    "secret-key",
			"audio_data": "base64-audio",
		},
	}, token)
	if asrResponse.Code != http.StatusCreated {
		t.Fatalf("asr status = %d, body = %s", asrResponse.Code, asrResponse.Body.String())
	}
	var asrBody struct {
		ASRResult ASRResult `json:"asr_result"`
	}
	if err := json.Unmarshal(asrResponse.Body.Bytes(), &asrBody); err != nil {
		t.Fatalf("decode asr response: %v", err)
	}
	if asrBody.ASRResult.RawResponseRedacted == nil {
		t.Fatal("expected raw_response_redacted")
	}
	if bytes.Contains(asrBody.ASRResult.RawResponseRedacted, []byte("secret-key")) || bytes.Contains(asrBody.ASRResult.RawResponseRedacted, []byte("base64-audio")) {
		t.Fatalf("raw response was not redacted: %s", string(asrBody.ASRResult.RawResponseRedacted))
	}

	correctionResponse := performJSON(router, http.MethodPatch, "/api/sessions/session_001/turns/turn_001/asr-results/asr_001/correction", map[string]any{
		"corrected_transcript": "I come from Hangzhou, a city in eastern China.",
	}, token)
	if correctionResponse.Code != http.StatusOK {
		t.Fatalf("asr correction status = %d, body = %s", correctionResponse.Code, correctionResponse.Body.String())
	}
	var correctionBody struct {
		ASRResult ASRResult `json:"asr_result"`
	}
	if err := json.Unmarshal(correctionResponse.Body.Bytes(), &correctionBody); err != nil {
		t.Fatalf("decode correction response: %v", err)
	}
	if correctionBody.ASRResult.CorrectedTranscript == nil || *correctionBody.ASRResult.CorrectedTranscript != "I come from Hangzhou, a city in eastern China." {
		t.Fatalf("corrected transcript = %v", correctionBody.ASRResult.CorrectedTranscript)
	}

	metricsResponse := performJSON(router, http.MethodPost, "/api/sessions/session_001/turns/turn_001/speech-metrics", map[string]any{
		"audio_asset_id":          "audio_001",
		"transcript":              "Um I mean I come from Hangzhou and I like it.",
		"duration_ms":             18000,
		"long_pause_threshold_ms": 1000,
		"pause_segments": []map[string]any{
			{"start_ms": 1000, "end_ms": 1600},
			{"start_ms": 3000, "end_ms": 4600},
		},
		"asr_confidence": 0.91,
	}, token)
	if metricsResponse.Code != http.StatusCreated {
		t.Fatalf("metrics status = %d, body = %s", metricsResponse.Code, metricsResponse.Body.String())
	}
	var metricsBody struct {
		SpeechMetrics SpeechMetrics `json:"speech_metrics"`
	}
	if err := json.Unmarshal(metricsResponse.Body.Bytes(), &metricsBody); err != nil {
		t.Fatalf("decode metrics response: %v", err)
	}
	if metricsBody.SpeechMetrics.DurationMS == nil || *metricsBody.SpeechMetrics.DurationMS != 18000 {
		t.Fatalf("duration_ms = %v", metricsBody.SpeechMetrics.DurationMS)
	}
	if metricsBody.SpeechMetrics.WordsCount == nil || *metricsBody.SpeechMetrics.WordsCount != 11 {
		t.Fatalf("words_count = %v", metricsBody.SpeechMetrics.WordsCount)
	}
	if metricsBody.SpeechMetrics.LongPauseCount == nil || *metricsBody.SpeechMetrics.LongPauseCount != 1 {
		t.Fatalf("long_pause_count = %v", metricsBody.SpeechMetrics.LongPauseCount)
	}
}

func TestRedactsASRRawResponse(t *testing.T) {
	payload, err := marshalRedactedObject(map[string]any{
		"id":            "provider_response_001",
		"authorization": "Bearer secret-token",
		"content": []any{
			map[string]any{
				"type":         "audio",
				"audio_base64": "UklGRg==",
			},
			map[string]any{
				"type": "text",
				"text": "I come from Hangzhou.",
			},
		},
	})
	if err != nil {
		t.Fatalf("marshalRedactedObject() error = %v", err)
	}

	text := string(payload)
	if bytes.Contains(payload, []byte("secret-token")) || bytes.Contains(payload, []byte("UklGRg==")) {
		t.Fatalf("payload was not redacted: %s", text)
	}
	if !bytes.Contains(payload, []byte("provider_response_001")) || !bytes.Contains(payload, []byte("I come from Hangzhou.")) {
		t.Fatalf("non-sensitive fields should remain: %s", text)
	}
}

func TestHandlerRequiresAuthentication(t *testing.T) {
	router, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/sessions", nil, "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func testRouter(t *testing.T) (http.Handler, string) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	tokenService, err := auth.NewTokenService(auth.TokenServiceConfig{Secret: "test-secret-must-be-at-least-32-bytes"})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}
	user := auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}
	pair, err := tokenService.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}

	router := gin.New()
	NewHandler(newFakeStore()).RegisterRoutes(router.Group("/api"), auth.NewAuthenticator(authStore{}, tokenService))
	return router, "Bearer " + pair.AccessToken
}

type fakeStore struct{}

func newFakeStore() fakeStore {
	return fakeStore{}
}

func (fakeStore) CreateSession(_ context.Context, userID string, input CreateSessionInput) (PracticeSession, error) {
	parts, err := plannedParts(input)
	if err != nil {
		return PracticeSession{}, err
	}
	session := baseSession(userID, input.Mode, StatusCreated)
	for index, part := range parts {
		session.Parts = append(session.Parts, SessionPart{ID: "part_001", SessionID: session.ID, Part: part, Status: StatusCreated, OrderIndex: index})
	}
	return session, nil
}

func (fakeStore) ListSessions(_ context.Context, userID string, _ SessionFilter) ([]PracticeSession, error) {
	return []PracticeSession{baseSession(userID, ModeFullExam, StatusCreated)}, nil
}

func (fakeStore) GetSession(_ context.Context, userID string, _ string) (PracticeSession, error) {
	return baseSession(userID, ModeFullExam, StatusCreated), nil
}

func (fakeStore) StartSession(_ context.Context, userID string, _ string) (PracticeSession, error) {
	return baseSession(userID, ModeFullExam, StatusInProgress), nil
}

func (fakeStore) CompletePart(_ context.Context, userID string, _ string, _ int) (PracticeSession, error) {
	return baseSession(userID, ModeFullExam, StatusInProgress), nil
}

func (fakeStore) FinishSession(_ context.Context, userID string, _ string) (PracticeSession, error) {
	return baseSession(userID, ModeFullExam, StatusScoring), nil
}

func (fakeStore) CancelSession(_ context.Context, userID string, _ string) (PracticeSession, error) {
	return baseSession(userID, ModeFullExam, StatusCancelled), nil
}

func (fakeStore) CreateTurn(_ context.Context, _ string, sessionID string, input CreateTurnInput) (SessionTurn, error) {
	return SessionTurn{ID: "turn_001", SessionID: sessionID, TurnIndex: 0, Speaker: input.Speaker, Status: input.Status, QuestionText: input.QuestionText, AnswerText: input.AnswerText, Metadata: json.RawMessage(`{}`)}, nil
}

func (fakeStore) UpdateTurn(_ context.Context, _ string, sessionID string, turnID string, input UpdateTurnInput) (SessionTurn, error) {
	status := TurnStatusCompleted
	if input.Status != nil {
		status = *input.Status
	}
	return SessionTurn{ID: turnID, SessionID: sessionID, TurnIndex: 0, Speaker: SpeakerUser, Status: status, Metadata: json.RawMessage(`{}`)}, nil
}

func (fakeStore) AttachAudioAsset(_ context.Context, userID string, sessionID string, turnID string, input AudioAssetInput) (AudioAsset, error) {
	return AudioAsset{ID: "audio_001", UserID: &userID, SessionID: &sessionID, TurnID: &turnID, Kind: input.Kind, StorageBucket: input.StorageBucket, StorageKey: input.StorageKey, MimeType: input.MimeType, SizeBytes: input.SizeBytes, CreatedAt: time.Now().UTC()}, nil
}

func (fakeStore) SaveASRResult(_ context.Context, _ string, _ string, turnID string, input ASRResultInput) (ASRResult, error) {
	rawResponse, err := marshalRedactedObject(input.RawResponse)
	if err != nil {
		return ASRResult{}, err
	}
	return ASRResult{ID: "asr_001", TurnID: turnID, AudioAssetID: input.AudioAssetID, Provider: input.Provider, Model: input.Model, Transcript: input.Transcript, Confidence: input.Confidence, Segments: json.RawMessage(`[]`), RawResponseRedacted: rawResponse, CreatedAt: time.Now().UTC()}, nil
}

func (fakeStore) CorrectASRResult(_ context.Context, userID string, _ string, turnID string, asrResultID string, input CorrectASRResultInput) (ASRResult, error) {
	now := time.Now().UTC()
	return ASRResult{ID: asrResultID, TurnID: turnID, Provider: "mock", Model: "mimo-v2.5-asr", Transcript: "I come from Hangzhou.", CorrectedTranscript: &input.CorrectedTranscript, CorrectedByUserID: &userID, CorrectedAt: &now, Segments: json.RawMessage(`[]`), RawResponseRedacted: json.RawMessage(`{}`), CreatedAt: now}, nil
}

func (fakeStore) SaveSpeechMetrics(_ context.Context, _ string, _ string, turnID string, input SpeechMetricsInput) (SpeechMetrics, error) {
	wordsCount := input.WordsCount
	if wordsCount == nil {
		value := countSpeechWords(input.Transcript)
		wordsCount = &value
	}
	durationMS := input.DurationMS
	wpm := input.WPM
	if wpm == nil && durationMS != nil && *durationMS > 0 && wordsCount != nil {
		value := roundFloat(float64(*wordsCount)/(float64(*durationMS)/60000), 2)
		wpm = &value
	}
	longPauseCount, meanPauseMS, totalPauseMS := derivePauseMetrics(input)
	fillerCount := input.FillerCount
	if fillerCount == nil {
		value := countSpeechFillers(input.Transcript)
		fillerCount = &value
	}
	fillerRatio := input.FillerRatio
	if fillerRatio == nil && wordsCount != nil && *wordsCount > 0 && fillerCount != nil {
		value := roundFloat(float64(*fillerCount)/float64(*wordsCount), 4)
		fillerRatio = &value
	}
	return SpeechMetrics{
		ID:             "metrics_001",
		TurnID:         turnID,
		AudioAssetID:   input.AudioAssetID,
		DurationMS:     durationMS,
		WordsCount:     wordsCount,
		WPM:            wpm,
		LongPauseCount: longPauseCount,
		MeanPauseMS:    meanPauseMS,
		TotalPauseMS:   totalPauseMS,
		FillerCount:    fillerCount,
		FillerRatio:    fillerRatio,
		ASRConfidence:  input.ASRConfidence,
		RawMetrics:     json.RawMessage(`{"computed_mvp":true}`),
		CreatedAt:      time.Now().UTC(),
	}, nil
}

func baseSession(userID string, mode string, status string) PracticeSession {
	return PracticeSession{ID: "session_001", UserID: userID, Mode: mode, Status: status, State: json.RawMessage(`{}`), CreatedAt: time.Now().UTC(), UpdatedAt: time.Now().UTC(), Parts: []SessionPart{}, Turns: []SessionTurn{}}
}

type authStore struct{}

func (authStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (authStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (authStore) GetUserByID(context.Context, string) (auth.User, error) {
	return auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}, nil
}

func (authStore) UpdateLastLogin(context.Context, string) error {
	return nil
}

func performJSON(router http.Handler, method string, path string, body any, authHeader string) *httptest.ResponseRecorder {
	var payload bytes.Buffer
	if body != nil {
		if err := json.NewEncoder(&payload).Encode(body); err != nil {
			panic(err)
		}
	}

	request := httptest.NewRequest(method, path, &payload)
	request.Header.Set("Content-Type", "application/json")
	if authHeader != "" {
		request.Header.Set("Authorization", authHeader)
	}

	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}
