package questionbank

import "context"

type Store interface {
	CreateSeason(ctx context.Context, input SeasonInput) (Season, error)
	ListSeasons(ctx context.Context, includeArchived bool) ([]Season, error)
	GetActiveSeason(ctx context.Context) (Season, error)
	UpdateSeason(ctx context.Context, id string, input SeasonInput) (Season, error)
	ActivateSeason(ctx context.Context, id string) (Season, error)
	ArchiveSeason(ctx context.Context, id string) error

	CreateTopic(ctx context.Context, input TopicInput) (Topic, error)
	ListTopics(ctx context.Context, includeDraft bool) ([]Topic, error)
	UpdateTopic(ctx context.Context, id string, input TopicInput) (Topic, error)
	ArchiveTopic(ctx context.Context, id string) error

	CreateQuestion(ctx context.Context, input QuestionInput, createdBy string) (Question, error)
	ListQuestions(ctx context.Context, filter QuestionFilter) ([]Question, error)
	GetQuestion(ctx context.Context, id string) (Question, error)
	UpdateQuestion(ctx context.Context, id string, input QuestionInput, changedBy string) (Question, error)
	ArchiveQuestion(ctx context.Context, id string) error
}
