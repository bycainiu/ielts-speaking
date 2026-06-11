package report

import "context"

type Store interface {
	SaveReport(ctx context.Context, userID string, sessionID string, input SaveReportInput) (ScoreReport, error)
	GetLatestReport(ctx context.Context, userID string, sessionID string) (ScoreReport, error)
	GetLatestReportForAdmin(ctx context.Context, sessionID string) (ScoreReport, error)
	ListReports(ctx context.Context, userID string, filter ReportHistoryFilter) ([]ReportHistoryItem, error)
	ListReportsForAdmin(ctx context.Context, filter ReportHistoryFilter) ([]ReportHistoryItem, error)
	SubmitReportFeedback(ctx context.Context, userID string, reportID string, input SubmitReportFeedbackInput) (ReportUserFeedback, error)
	ListReportFeedback(ctx context.Context, filter ReportFeedbackFilter) ([]ReportUserFeedback, error)
}
