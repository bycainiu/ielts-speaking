package report

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

func TestHandlerSaveAndGetLatestReport(t *testing.T) {
	router, token, store := testRouter(t)

	response := performJSON(router, http.MethodPost, "/api/sessions/session_001/report", makeReportPayload(), token)
	if response.Code != http.StatusCreated {
		t.Fatalf("save status = %d, body = %s", response.Code, response.Body.String())
	}
	if len(store.savedReports) != 1 {
		t.Fatalf("saved reports = %d, want 1", len(store.savedReports))
	}

	var saveBody struct {
		Report ScoreReport `json:"report"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &saveBody); err != nil {
		t.Fatalf("decode save response: %v", err)
	}
	if saveBody.Report.OverallBand == nil || *saveBody.Report.OverallBand != 6.5 {
		t.Fatalf("overall band = %v", saveBody.Report.OverallBand)
	}
	if len(saveBody.Report.Criteria) != 4 {
		t.Fatalf("criteria count = %d", len(saveBody.Report.Criteria))
	}
	if len(saveBody.Report.FeedbackItems) != 1 {
		t.Fatalf("feedback count = %d", len(saveBody.Report.FeedbackItems))
	}
	if len(saveBody.Report.ReferenceAnswers) != 1 {
		t.Fatalf("reference count = %d", len(saveBody.Report.ReferenceAnswers))
	}

	getResponse := performJSON(router, http.MethodGet, "/api/sessions/session_001/report", nil, token)
	if getResponse.Code != http.StatusOK {
		t.Fatalf("get status = %d, body = %s", getResponse.Code, getResponse.Body.String())
	}
}

func TestHandlerListReportHistory(t *testing.T) {
	router, token, store := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/reports?mode=part_practice&part=2&from=2026-06-01&to=2026-06-08&limit=12&offset=6", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("history status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.lastFilter.Mode != "part_practice" {
		t.Fatalf("mode = %q", store.lastFilter.Mode)
	}
	if store.lastFilter.Part == nil || *store.lastFilter.Part != 2 {
		t.Fatalf("part = %v", store.lastFilter.Part)
	}
	if store.lastFilter.From == nil || store.lastFilter.From.Format("2006-01-02") != "2026-06-01" {
		t.Fatalf("from = %v", store.lastFilter.From)
	}
	if store.lastFilter.To == nil || store.lastFilter.To.Format("2006-01-02") != "2026-06-09" {
		t.Fatalf("to = %v", store.lastFilter.To)
	}
	if store.lastFilter.Limit != 12 || store.lastFilter.Offset != 6 {
		t.Fatalf("pagination = %d/%d", store.lastFilter.Limit, store.lastFilter.Offset)
	}

	var body struct {
		Reports []ReportHistoryItem `json:"reports"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode history response: %v", err)
	}
	if len(body.Reports) != 2 {
		t.Fatalf("reports = %d, want 2", len(body.Reports))
	}
	if body.Reports[0].SessionID == "" || body.Reports[0].OverallBand == nil {
		t.Fatalf("history item missing session or band: %+v", body.Reports[0])
	}
}

func TestHandlerRejectsInvalidHistoryFilter(t *testing.T) {
	router, token, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/reports?part=4", nil, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerRejectsMissingCriterion(t *testing.T) {
	router, token, _ := testRouter(t)
	payload := makeReportPayload()
	delete(payload["criteria"].(map[string]any), "pronunciation")

	response := performJSON(router, http.MethodPost, "/api/sessions/session_001/report", payload, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerRequiresAuthentication(t *testing.T) {
	router, _, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/sessions/session_001/report", nil, "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestHandlerSubmitReportFeedback(t *testing.T) {
	router, token, store := testRouter(t)
	comment := "The score explanation was useful."
	payload := map[string]any{
		"target_type": "overall",
		"vote":        "up",
		"comment":     comment,
		"metadata": map[string]any{
			"surface": "report_page",
		},
	}

	response := performJSON(router, http.MethodPost, "/api/reports/report_001/feedback", payload, token)
	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if len(store.feedback) != 1 {
		t.Fatalf("feedback count = %d, want 1", len(store.feedback))
	}
	if store.feedback[0].UserID != "user_001" || store.feedback[0].ReportID != "report_001" {
		t.Fatalf("stored feedback has wrong owner/report: %+v", store.feedback[0])
	}

	var body struct {
		Feedback ReportUserFeedback `json:"feedback"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode feedback response: %v", err)
	}
	if body.Feedback.TargetType != "overall" || body.Feedback.TargetID != nil || body.Feedback.Vote != "up" {
		t.Fatalf("feedback response = %+v", body.Feedback)
	}
	if body.Feedback.Comment == nil || *body.Feedback.Comment != comment {
		t.Fatalf("comment = %v", body.Feedback.Comment)
	}
}

func TestHandlerRejectsInvalidReportFeedback(t *testing.T) {
	router, token, _ := testRouter(t)
	payload := map[string]any{
		"target_type": "feedback",
		"vote":        "up",
	}

	response := performJSON(router, http.MethodPost, "/api/reports/report_001/feedback", payload, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func TestHandlerRequiresAuthenticationForFeedback(t *testing.T) {
	router, _, _ := testRouter(t)

	response := performJSON(router, http.MethodPost, "/api/reports/report_001/feedback", map[string]any{
		"target_type": "overall",
		"vote":        "down",
	}, "")
	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusUnauthorized)
	}
}

func TestHandlerExportReportFeedback(t *testing.T) {
	operator := auth.User{ID: "operator_001", Email: "operator@example.com", Role: "operator", Status: "active", CreatedAt: time.Now().UTC()}
	router, token, store := testRouterWithUser(t, operator)
	targetID := "11111111-1111-1111-1111-111111111111"
	store.feedback = append(store.feedback, ReportUserFeedback{
		ID:         "feedback_001",
		ReportID:   "report_001",
		SessionID:  "session_001",
		UserID:     "user_001",
		TargetType: "feedback",
		TargetID:   &targetID,
		Vote:       "down",
		Metadata:   json.RawMessage(`{"surface":"report_page"}`),
		CreatedAt:  time.Now().UTC(),
	})

	response := performJSON(router, http.MethodGet, "/api/reports/feedback/export?target_type=feedback&vote=down&limit=20&offset=5", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.lastFeedbackFilter.TargetType != "feedback" || store.lastFeedbackFilter.Vote != "down" {
		t.Fatalf("filter = %+v", store.lastFeedbackFilter)
	}
	if store.lastFeedbackFilter.Limit != 20 || store.lastFeedbackFilter.Offset != 5 {
		t.Fatalf("pagination = %d/%d", store.lastFeedbackFilter.Limit, store.lastFeedbackFilter.Offset)
	}

	var body struct {
		Feedback []ReportUserFeedback `json:"feedback"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &body); err != nil {
		t.Fatalf("decode export response: %v", err)
	}
	if len(body.Feedback) != 1 || body.Feedback[0].TargetType != "feedback" {
		t.Fatalf("feedback export = %+v", body.Feedback)
	}
}

func TestHandlerExportReportFeedbackRequiresOperator(t *testing.T) {
	router, token, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/reports/feedback/export", nil, token)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
}

func TestHandlerAdminListReportsRequiresOperator(t *testing.T) {
	router, token, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/admin/reports", nil, token)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
}

func TestHandlerAdminListReportsCanFilterAllUsers(t *testing.T) {
	admin := auth.User{ID: "admin_001", Email: "admin@example.com", Role: "admin", Status: "active", CreatedAt: time.Now().UTC()}
	router, token, store := testRouterWithUser(t, admin)
	userID := "11111111-1111-1111-1111-111111111111"
	sessionID := "22222222-2222-2222-2222-222222222222"

	response := performJSON(router, http.MethodGet, "/api/admin/reports?user_id="+userID+"&session_id="+sessionID+"&mode=full_exam&limit=10", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.lastAdminFilter.UserID != userID || store.lastAdminFilter.SessionID != sessionID || store.lastAdminFilter.Mode != "full_exam" {
		t.Fatalf("admin filter = %+v", store.lastAdminFilter)
	}
}

func TestHandlerAdminListReportsRejectsInvalidUUIDFilter(t *testing.T) {
	admin := auth.User{ID: "admin_001", Email: "admin@example.com", Role: "admin", Status: "active", CreatedAt: time.Now().UTC()}
	router, token, _ := testRouterWithUser(t, admin)

	response := performJSON(router, http.MethodGet, "/api/admin/reports?session_id=not-a-uuid", nil, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want %d, body = %s", response.Code, http.StatusBadRequest, response.Body.String())
	}
}

func TestHandlerAdminGetLatestReportRequiresOperator(t *testing.T) {
	router, token, _ := testRouter(t)

	response := performJSON(router, http.MethodGet, "/api/admin/sessions/session_001/report", nil, token)
	if response.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want %d", response.Code, http.StatusForbidden)
	}
}

func TestHandlerAdminGetLatestReportCanReadAnySession(t *testing.T) {
	operator := auth.User{ID: "operator_001", Email: "operator@example.com", Role: "operator", Status: "active", CreatedAt: time.Now().UTC()}
	router, token, store := testRouterWithUser(t, operator)

	response := performJSON(router, http.MethodGet, "/api/admin/sessions/session_foreign/report", nil, token)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
	if store.lastAdminReportSessionID != "session_foreign" {
		t.Fatalf("admin report session = %q", store.lastAdminReportSessionID)
	}
}

func TestHandlerRejectsInvalidReportFeedbackExportFilter(t *testing.T) {
	admin := auth.User{ID: "admin_001", Email: "admin@example.com", Role: "admin", Status: "active", CreatedAt: time.Now().UTC()}
	router, token, _ := testRouterWithUser(t, admin)

	response := performJSON(router, http.MethodGet, "/api/reports/feedback/export?target_type=unknown", nil, token)
	if response.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, body = %s", response.Code, response.Body.String())
	}
}

func testRouter(t *testing.T) (http.Handler, string, *fakeStore) {
	user := auth.User{ID: "user_001", Email: "learner@example.com", Role: "user", Status: "active", CreatedAt: time.Now().UTC()}
	return testRouterWithUser(t, user)
}

func testRouterWithUser(t *testing.T, user auth.User) (http.Handler, string, *fakeStore) {
	t.Helper()
	gin.SetMode(gin.TestMode)

	tokenService, err := auth.NewTokenService(auth.TokenServiceConfig{Secret: "test-secret-must-be-at-least-32-bytes"})
	if err != nil {
		t.Fatalf("NewTokenService() error = %v", err)
	}
	pair, err := tokenService.GeneratePair(user)
	if err != nil {
		t.Fatalf("GeneratePair() error = %v", err)
	}

	store := &fakeStore{}
	router := gin.New()
	NewHandler(store).RegisterRoutes(router.Group("/api"), auth.NewAuthenticator(authStore{users: map[string]auth.User{user.ID: user}}, tokenService))
	return router, "Bearer " + pair.AccessToken, store
}

type fakeStore struct {
	savedReports             []SaveReportInput
	lastFilter               ReportHistoryFilter
	lastAdminFilter          ReportHistoryFilter
	lastAdminReportSessionID string
	feedback                 []ReportUserFeedback
	lastFeedbackFilter       ReportFeedbackFilter
}

func (s *fakeStore) SaveReport(_ context.Context, userID string, sessionID string, input SaveReportInput) (ScoreReport, error) {
	input.Normalize()
	if err := input.Validate(sessionID); err != nil {
		return ScoreReport{}, err
	}
	s.savedReports = append(s.savedReports, input)
	return fakeReport(userID, sessionID, input), nil
}

func (s *fakeStore) GetLatestReport(_ context.Context, userID string, sessionID string) (ScoreReport, error) {
	if len(s.savedReports) == 0 {
		input := SaveReportInput{}
		payload := makeReportPayload()
		bytes, _ := json.Marshal(payload)
		_ = json.Unmarshal(bytes, &input)
		input.Normalize()
		s.savedReports = append(s.savedReports, input)
	}
	return fakeReport(userID, sessionID, s.savedReports[len(s.savedReports)-1]), nil
}

func (s *fakeStore) GetLatestReportForAdmin(_ context.Context, sessionID string) (ScoreReport, error) {
	s.lastAdminReportSessionID = sessionID
	if len(s.savedReports) == 0 {
		input := SaveReportInput{}
		payload := makeReportPayload()
		bytes, _ := json.Marshal(payload)
		_ = json.Unmarshal(bytes, &input)
		input.Normalize()
		s.savedReports = append(s.savedReports, input)
	}
	return fakeReport("foreign_user_001", sessionID, s.savedReports[len(s.savedReports)-1]), nil
}

func (s *fakeStore) ListReports(_ context.Context, _ string, filter ReportHistoryFilter) ([]ReportHistoryItem, error) {
	s.lastFilter = filter
	return []ReportHistoryItem{
		fakeHistoryItem("report_001", "session_001", "full_exam", nil, 6.5, time.Now().Add(-24*time.Hour)),
		fakeHistoryItem("report_002", "session_002", "part_practice", intPtr(2), 7.0, time.Now()),
	}, nil
}

func (s *fakeStore) ListReportsForAdmin(_ context.Context, filter ReportHistoryFilter) ([]ReportHistoryItem, error) {
	s.lastAdminFilter = filter
	return []ReportHistoryItem{
		fakeHistoryItem("report_001", "session_001", "full_exam", nil, 6.5, time.Now().Add(-24*time.Hour)),
		fakeHistoryItem("report_002", "session_002", "part_practice", intPtr(2), 7.0, time.Now()),
	}, nil
}

func (s *fakeStore) SubmitReportFeedback(_ context.Context, userID string, reportID string, input SubmitReportFeedbackInput) (ReportUserFeedback, error) {
	input.Normalize()
	if err := input.Validate(); err != nil {
		return ReportUserFeedback{}, err
	}
	metadata, err := marshalObject(input.Metadata)
	if err != nil {
		return ReportUserFeedback{}, err
	}
	item := ReportUserFeedback{
		ID:         "feedback_001",
		ReportID:   reportID,
		SessionID:  "session_001",
		UserID:     userID,
		TargetType: input.TargetType,
		TargetID:   input.TargetID,
		Vote:       input.Vote,
		Comment:    input.Comment,
		Metadata:   json.RawMessage(metadata),
		CreatedAt:  time.Now().UTC(),
	}
	s.feedback = append(s.feedback, item)
	return item, nil
}

func (s *fakeStore) ListReportFeedback(_ context.Context, filter ReportFeedbackFilter) ([]ReportUserFeedback, error) {
	s.lastFeedbackFilter = filter
	if len(s.feedback) == 0 {
		s.feedback = append(s.feedback, ReportUserFeedback{
			ID:         "feedback_001",
			ReportID:   "report_001",
			SessionID:  "session_001",
			UserID:     "user_001",
			TargetType: "overall",
			Vote:       "up",
			Metadata:   json.RawMessage(`{}`),
			CreatedAt:  time.Now().UTC(),
		})
	}
	return s.feedback, nil
}

func fakeReport(userID string, sessionID string, input SaveReportInput) ScoreReport {
	now := time.Now().UTC()
	rawReport, _ := buildRawReportPayload(input)
	criteria := []CriterionScore{}
	for _, criterion := range requiredCriteria {
		score := input.Criteria[criterion]
		evidence, _ := json.Marshal(score.Evidence)
		suggestions, _ := json.Marshal(score.Suggestions)
		rawOutput, _ := json.Marshal(score.RawOutput)
		criteria = append(criteria, CriterionScore{
			ID:          "criterion_" + criterion,
			ReportID:    "report_001",
			Criterion:   criterion,
			Band:        score.Band,
			Confidence:  score.Confidence,
			Evidence:    evidence,
			Suggestions: suggestions,
			RawOutput:   rawOutput,
			CreatedAt:   now,
		})
	}
	feedbackItems := []FeedbackItem{}
	for index, item := range input.FeedbackItems {
		evidenceRefs, _ := json.Marshal(item.EvidenceRefs)
		feedbackItems = append(feedbackItems, FeedbackItem{
			ID:           "feedback_001",
			ReportID:     "report_001",
			Category:     item.Category,
			Priority:     index + 1,
			Title:        item.Title,
			Body:         item.Body,
			EvidenceRefs: evidenceRefs,
			CreatedAt:    now,
		})
	}
	referenceAnswers := []ReferenceAnswer{}
	for _, item := range input.ReferenceAnswers {
		skeleton, _ := json.Marshal(item.Skeleton)
		referenceAnswers = append(referenceAnswers, ReferenceAnswer{
			ID:                   "reference_001",
			ReportID:             "report_001",
			TurnID:               item.TurnID,
			BandTarget:           item.BandTarget,
			Skeleton:             skeleton,
			AnswerText:           item.AnswerText,
			PersonalizationNotes: item.PersonalizationNotes,
			CreatedAt:            now,
		})
	}
	studyPlans := []StudyPlan{}
	for _, item := range input.NextPracticePlan {
		studyPlans = append(studyPlans, StudyPlan{
			ID:        "plan_001",
			ReportID:  stringPtr("report_001"),
			UserID:    userID,
			Priority:  item.Priority,
			Focus:     item.Focus,
			Task:      item.Task,
			DueOn:     item.DueOn,
			Status:    "planned",
			CreatedAt: now,
			UpdatedAt: now,
		})
	}
	return ScoreReport{
		ID:               "report_001",
		SessionID:        sessionID,
		Version:          input.Version,
		Status:           input.Status,
		OverallBand:      input.OverallBand,
		Confidence:       input.Confidence,
		Disclaimer:       input.Disclaimer,
		ModelRunID:       input.ModelRunID,
		RawReport:        rawReport,
		CreatedAt:        now,
		UpdatedAt:        now,
		Criteria:         criteria,
		FeedbackItems:    feedbackItems,
		ReferenceAnswers: referenceAnswers,
		StudyPlans:       studyPlans,
	}
}

func fakeHistoryItem(reportID string, sessionID string, mode string, targetPart *int, overallBand float64, createdAt time.Time) ReportHistoryItem {
	confidence := 0.8
	return ReportHistoryItem{
		ID:               reportID,
		SessionID:        sessionID,
		UserID:           "user_001",
		Mode:             mode,
		SessionStatus:    "completed",
		TargetPart:       targetPart,
		Version:          1,
		ReportStatus:     StatusReady,
		OverallBand:      &overallBand,
		Confidence:       &confidence,
		Criteria:         json.RawMessage(`{"fluency_coherence":{"band":6.5,"confidence":0.8}}`),
		SessionCreatedAt: createdAt.Add(-30 * time.Minute),
		ReportCreatedAt:  createdAt,
		ReportUpdatedAt:  createdAt,
	}
}

func makeReportPayload() map[string]any {
	criterion := map[string]any{
		"band":       6.5,
		"confidence": 0.82,
		"evidence": []map[string]any{
			{"turn_id": "turn_1", "quote": "I think it is useful.", "reason": "clear answer"},
		},
		"suggestions": []string{"Add one more specific example."},
		"raw_output":  map[string]any{"source": "test"},
	}
	return map[string]any{
		"version":      1,
		"status":       "ready",
		"overall_band": 6.5,
		"confidence":   0.8,
		"criteria": map[string]any{
			"fluency_coherence":          criterion,
			"lexical_resource":           criterion,
			"grammatical_range_accuracy": criterion,
			"pronunciation":              criterion,
		},
		"reviewer_notes": []string{"Use conservative scoring."},
		"next_practice_plan": []map[string]any{
			{"priority": 1, "focus": "fluency", "task": "Record a 90-second answer."},
		},
		"feedback_items": []map[string]any{
			{
				"category":      "fluency_coherence",
				"priority":      1,
				"title":         "Reduce long pauses",
				"body":          "Plan the next sentence before speaking.",
				"evidence_refs": []map[string]any{{"turn_id": "turn_1"}},
			},
		},
		"reference_answers": []map[string]any{
			{
				"turn_id":               "turn_1",
				"band_target":           7.0,
				"skeleton":              map[string]any{"opening": "direct answer"},
				"answer_text":           "I would give a direct answer and then add one example.",
				"personalization_notes": "Do not memorize this answer word for word.",
			},
		},
		"disclaimer":   IELTSDisclaimer,
		"model_run_id": "run_001",
		"raw_report":   map[string]any{"workflow_version": "scoring_workflow.v1"},
	}
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

func stringPtr(value string) *string {
	return &value
}

func intPtr(value int) *int {
	return &value
}

type authStore struct {
	users map[string]auth.User
}

func (authStore) CreateUser(context.Context, auth.CreateUserParams) (auth.User, error) {
	return auth.User{}, nil
}

func (authStore) GetUserByEmail(context.Context, string) (auth.UserWithPassword, error) {
	return auth.UserWithPassword{}, auth.ErrUserNotFound
}

func (s authStore) GetUserByID(_ context.Context, userID string) (auth.User, error) {
	if user, ok := s.users[userID]; ok {
		return user, nil
	}
	return auth.User{}, auth.ErrUserNotFound
}

func (authStore) UpdateLastLogin(context.Context, string) error {
	return nil
}
