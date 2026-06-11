package adminops

import "context"

type Store interface {
	RecordAdminAudit(ctx context.Context, input AdminAuditInput) error
	ListAdminAudits(ctx context.Context, filter AdminAuditLogFilter) ([]AdminAuditLog, error)

	CreateKnowledgeDoc(ctx context.Context, input KnowledgeDocInput, actorUserID string) (KnowledgeDoc, error)
	ListKnowledgeDocs(ctx context.Context, filter KnowledgeDocFilter) ([]KnowledgeDoc, error)
	UpdateKnowledgeDoc(ctx context.Context, id string, input KnowledgeDocUpdateInput, actorUserID string) (KnowledgeDoc, error)
	ReindexKnowledgeDoc(ctx context.Context, id string, actorUserID string) (KnowledgeDoc, error)
	ArchiveKnowledgeDoc(ctx context.Context, id string) error

	ListPromptVersions(ctx context.Context, filter PromptVersionFilter) ([]PromptVersion, error)

	ContentReviewSummary(ctx context.Context) ([]ContentReviewSummaryItem, error)
	ListReferenceAnswers(ctx context.Context, filter ReferenceAnswerFilter) ([]ReferenceAnswerReview, error)
	UpdateReferenceAnswerStatus(ctx context.Context, id string, status string) (ReferenceAnswerReview, error)
}
