package adminops

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"

	"golang.org/x/crypto/blake2b"
)

const (
	chunkMaxChars        = 1200
	chunkOverlapChars    = 120
	embeddingDimension   = 1536
	embeddingModel       = "hash-embedding-v1"
	knowledgeSourceAdmin = "admin_upload"
)

var tokenPattern = regexp.MustCompile(`[A-Za-z0-9_]+`)

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) PostgresStore {
	return PostgresStore{db: db}
}

func (s PostgresStore) RecordAdminAudit(ctx context.Context, input AdminAuditInput) error {
	metadata, err := marshalMetadata(input.Metadata)
	if err != nil {
		return err
	}
	_, err = s.db.ExecContext(ctx, `
		insert into admin_audit_logs
			(actor_user_id, actor_role, action, resource, method, path, status_code, metadata)
		values
			(nullif($1, '')::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb)
	`, input.ActorUserID, input.ActorRole, input.Action, input.Resource, input.Method, input.Path, input.StatusCode, metadata)
	return mapError(err)
}

func (s PostgresStore) ListAdminAudits(ctx context.Context, filter AdminAuditLogFilter) ([]AdminAuditLog, error) {
	filter = normalizeAdminAuditLogFilter(filter)
	conditions := []string{"1 = 1"}
	args := []any{}
	if filter.Resource != "" {
		args = append(args, filter.Resource)
		conditions = append(conditions, fmt.Sprintf("resource = $%d", len(args)))
	}
	if filter.ActorRole != "" {
		args = append(args, filter.ActorRole)
		conditions = append(conditions, fmt.Sprintf("actor_role = $%d", len(args)))
	}
	if filter.Method != "" {
		args = append(args, filter.Method)
		conditions = append(conditions, fmt.Sprintf("method = $%d", len(args)))
	}
	if filter.StatusClass != 0 {
		lower := filter.StatusClass * 100
		upper := lower + 99
		args = append(args, lower, upper)
		conditions = append(conditions, fmt.Sprintf("status_code between $%d and $%d", len(args)-1, len(args)))
	}
	if filter.Query != "" {
		args = append(args, "%"+filter.Query+"%")
		conditions = append(
			conditions,
			fmt.Sprintf("(action ilike $%d or resource ilike $%d or path ilike $%d or metadata::text ilike $%d)", len(args), len(args), len(args), len(args)),
		)
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select id::text, actor_user_id::text, actor_role, action, resource, method, path, status_code, metadata, created_at
		from admin_audit_logs
		where %s
		order by created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	logs := []AdminAuditLog{}
	for rows.Next() {
		item, err := scanAdminAuditLog(rows)
		if err != nil {
			return nil, err
		}
		logs = append(logs, item)
	}
	return logs, rows.Err()
}

func (s PostgresStore) CreateKnowledgeDoc(ctx context.Context, input KnowledgeDocInput, actorUserID string) (KnowledgeDoc, error) {
	input = normalizeKnowledgeDocInput(input)
	if err := validateKnowledgeDocInput(input); err != nil {
		return KnowledgeDoc{}, err
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeDoc{}, err
	}
	defer tx.Rollback()

	metadata := knowledgeMetadata(input.Metadata, input.DocType, input.Status, actorUserID, "indexed")
	contentHash := hashContent(input.Content)
	var id string
	if err := tx.QueryRowContext(ctx, `
		insert into knowledge_docs (doc_type, title, content_hash, metadata, status)
		values ($1::knowledge_doc_type, $2, $3, $4::jsonb, $5::content_status)
		returning id::text
	`, input.DocType, input.Title, contentHash, mustJSON(metadata), input.Status).Scan(&id); err != nil {
		return KnowledgeDoc{}, mapError(err)
	}

	if err := replaceKnowledgeChunks(ctx, tx, id, input.DocType, input.Title, input.Status, input.Content, metadata); err != nil {
		return KnowledgeDoc{}, mapError(err)
	}

	if err := tx.Commit(); err != nil {
		return KnowledgeDoc{}, err
	}

	return s.getKnowledgeDoc(ctx, id)
}

func (s PostgresStore) ListKnowledgeDocs(ctx context.Context, filter KnowledgeDocFilter) ([]KnowledgeDoc, error) {
	filter = normalizeKnowledgeDocFilter(filter)
	conditions := []string{"kd.deleted_at is null"}
	args := []any{}
	if filter.DocType != "" {
		args = append(args, filter.DocType)
		conditions = append(conditions, fmt.Sprintf("kd.doc_type = $%d::knowledge_doc_type", len(args)))
	}
	if filter.Status != "" {
		args = append(args, filter.Status)
		conditions = append(conditions, fmt.Sprintf("kd.status = $%d::content_status", len(args)))
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select
			kd.id::text, kd.doc_type::text, kd.owner_user_id::text, kd.source_id::text,
			kd.title, kd.content_hash, kd.metadata, kd.status::text,
			coalesce(count(kc.id), 0)::int,
			coalesce(sum(coalesce(kc.token_count, 0)), 0)::int,
			max(kc.embedding_model),
			kd.created_at, kd.updated_at, kd.deleted_at
		from knowledge_docs kd
		left join knowledge_chunks kc on kc.doc_id = kd.id
		where %s
		group by kd.id
		order by kd.updated_at desc, kd.created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	docs := []KnowledgeDoc{}
	for rows.Next() {
		doc, err := scanKnowledgeDoc(rows)
		if err != nil {
			return nil, err
		}
		docs = append(docs, doc)
	}
	return docs, rows.Err()
}

func (s PostgresStore) UpdateKnowledgeDoc(ctx context.Context, id string, input KnowledgeDocUpdateInput, actorUserID string) (KnowledgeDoc, error) {
	input = normalizeKnowledgeDocUpdateInput(input)
	if err := validateKnowledgeDocUpdateInput(input); err != nil {
		return KnowledgeDoc{}, err
	}

	current, err := s.getKnowledgeDoc(ctx, id)
	if err != nil {
		return KnowledgeDoc{}, err
	}
	docType := current.DocType
	content := ""
	if input.Content != nil {
		content = strings.TrimSpace(*input.Content)
	}
	metadata := knowledgeMetadata(input.Metadata, docType, input.Status, actorUserID, "indexed")

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeDoc{}, err
	}
	defer tx.Rollback()

	contentHash := current.ContentHash
	if input.Content != nil {
		contentHash = hashContent(content)
	}
	if _, err := tx.ExecContext(ctx, `
		update knowledge_docs
		set title = $2,
			content_hash = $3,
			metadata = $4::jsonb,
			status = $5::content_status,
			updated_at = now()
		where id = $1::uuid and deleted_at is null
	`, id, input.Title, contentHash, mustJSON(metadata), input.Status); err != nil {
		return KnowledgeDoc{}, mapError(err)
	}

	if input.Content != nil {
		if err := replaceKnowledgeChunks(ctx, tx, id, docType, input.Title, input.Status, content, metadata); err != nil {
			return KnowledgeDoc{}, mapError(err)
		}
	} else {
		if _, err := tx.ExecContext(ctx, `
			update knowledge_chunks
			set metadata = metadata || $2::jsonb
			where doc_id = $1::uuid
		`, id, mustJSON(map[string]any{"status": input.Status, "title": input.Title})); err != nil {
			return KnowledgeDoc{}, mapError(err)
		}
	}

	if err := tx.Commit(); err != nil {
		return KnowledgeDoc{}, err
	}

	return s.getKnowledgeDoc(ctx, id)
}

func (s PostgresStore) ReindexKnowledgeDoc(ctx context.Context, id string, actorUserID string) (KnowledgeDoc, error) {
	current, err := s.getKnowledgeDoc(ctx, id)
	if err != nil {
		return KnowledgeDoc{}, err
	}

	rows, err := s.db.QueryContext(ctx, `
		select content
		from knowledge_chunks
		where doc_id = $1::uuid
		order by chunk_index asc
	`, id)
	if err != nil {
		return KnowledgeDoc{}, mapError(err)
	}
	defer rows.Close()

	pieces := []string{}
	for rows.Next() {
		var content string
		if err := rows.Scan(&content); err != nil {
			return KnowledgeDoc{}, mapError(err)
		}
		pieces = append(pieces, content)
	}
	if err := rows.Err(); err != nil {
		return KnowledgeDoc{}, err
	}
	if len(pieces) == 0 {
		return KnowledgeDoc{}, fmt.Errorf("%w: no chunks available to rebuild", ErrInvalidInput)
	}

	content := strings.Join(pieces, "\n\n")
	metadata := copyMetadata(current.Metadata)
	metadata["index_status"] = "indexed"
	metadata["last_reindexed_at"] = time.Now().UTC().Format(time.RFC3339)
	if actorUserID != "" {
		metadata["last_reindexed_by"] = actorUserID
	}

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return KnowledgeDoc{}, err
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(ctx, `
		update knowledge_docs
		set content_hash = $2,
			metadata = $3::jsonb,
			updated_at = now()
		where id = $1::uuid and deleted_at is null
	`, id, hashContent(content), mustJSON(metadata)); err != nil {
		return KnowledgeDoc{}, mapError(err)
	}
	if err := replaceKnowledgeChunkPieces(ctx, tx, id, current.DocType, current.Title, current.Status, pieces, metadata); err != nil {
		return KnowledgeDoc{}, mapError(err)
	}
	if err := tx.Commit(); err != nil {
		return KnowledgeDoc{}, err
	}

	return s.getKnowledgeDoc(ctx, id)
}

func (s PostgresStore) ArchiveKnowledgeDoc(ctx context.Context, id string) error {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	if _, err := tx.ExecContext(ctx, `delete from knowledge_chunks where doc_id = $1::uuid`, id); err != nil {
		return mapError(err)
	}
	result, err := tx.ExecContext(ctx, `
		update knowledge_docs
		set status = 'archived',
			deleted_at = now(),
			updated_at = now()
		where id = $1::uuid and deleted_at is null
	`, id)
	if err != nil {
		return mapError(err)
	}
	affected, _ := result.RowsAffected()
	if affected == 0 {
		return ErrNotFound
	}
	return tx.Commit()
}

func (s PostgresStore) ListPromptVersions(ctx context.Context, filter PromptVersionFilter) ([]PromptVersion, error) {
	filter = normalizePromptVersionFilter(filter)
	conditions := []string{"1 = 1"}
	args := []any{}
	if filter.AgentName != "" {
		args = append(args, filter.AgentName)
		conditions = append(conditions, fmt.Sprintf("agent_name = $%d", len(args)))
	}
	if filter.Purpose != "" {
		args = append(args, filter.Purpose)
		conditions = append(conditions, fmt.Sprintf("purpose = $%d", len(args)))
	}
	if filter.Active != nil {
		args = append(args, *filter.Active)
		conditions = append(conditions, fmt.Sprintf("active = $%d", len(args)))
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select id::text, agent_name, purpose, version, content_hash, metadata, active, created_at
		from prompt_versions
		where %s
		order by active desc, agent_name asc, purpose asc, created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	versions := []PromptVersion{}
	for rows.Next() {
		version, err := scanPromptVersion(rows)
		if err != nil {
			return nil, err
		}
		versions = append(versions, version)
	}
	return versions, rows.Err()
}

func (s PostgresStore) ContentReviewSummary(ctx context.Context) ([]ContentReviewSummaryItem, error) {
	rows, err := s.db.QueryContext(ctx, `
		select 'question' as content_type, review_status::text as status, count(*)::int
		from questions
		where deleted_at is null
		group by review_status
		union all
		select 'knowledge_doc' as content_type, status::text, count(*)::int
		from knowledge_docs
		where deleted_at is null
		group by status
		union all
		select 'reference_answer' as content_type, review_status::text, count(*)::int
		from reference_answers
		group by review_status
		order by content_type asc, status asc
	`)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []ContentReviewSummaryItem{}
	for rows.Next() {
		var item ContentReviewSummaryItem
		if err := rows.Scan(&item.ContentType, &item.Status, &item.Count); err != nil {
			return nil, mapError(err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) ListReferenceAnswers(ctx context.Context, filter ReferenceAnswerFilter) ([]ReferenceAnswerReview, error) {
	filter = normalizeReferenceAnswerFilter(filter)
	conditions := []string{"1 = 1"}
	args := []any{}
	if filter.Status != "" {
		args = append(args, filter.Status)
		conditions = append(conditions, fmt.Sprintf("review_status = $%d::content_status", len(args)))
	}
	args = append(args, filter.Limit, filter.Offset)
	query := fmt.Sprintf(`
		select id::text, report_id::text, turn_id::text, band_target::float8, skeleton,
			answer_text, personalization_notes, review_status::text, created_at
		from reference_answers
		where %s
		order by created_at desc
		limit $%d offset $%d
	`, strings.Join(conditions, " and "), len(args)-1, len(args))

	rows, err := s.db.QueryContext(ctx, query, args...)
	if err != nil {
		return nil, mapError(err)
	}
	defer rows.Close()

	items := []ReferenceAnswerReview{}
	for rows.Next() {
		item, err := scanReferenceAnswerReview(rows)
		if err != nil {
			return nil, err
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s PostgresStore) UpdateReferenceAnswerStatus(ctx context.Context, id string, status string) (ReferenceAnswerReview, error) {
	if _, ok := allowedStatuses[status]; !ok {
		return ReferenceAnswerReview{}, fmt.Errorf("%w: unsupported status", ErrInvalidInput)
	}
	item, err := scanReferenceAnswerReview(s.db.QueryRowContext(ctx, `
		update reference_answers
		set review_status = $2::content_status
		where id = $1::uuid
		returning id::text, report_id::text, turn_id::text, band_target::float8, skeleton,
			answer_text, personalization_notes, review_status::text, created_at
	`, id, status))
	if err != nil {
		return ReferenceAnswerReview{}, err
	}
	return item, nil
}

func (s PostgresStore) getKnowledgeDoc(ctx context.Context, id string) (KnowledgeDoc, error) {
	return scanKnowledgeDoc(s.db.QueryRowContext(ctx, `
		select
			kd.id::text, kd.doc_type::text, kd.owner_user_id::text, kd.source_id::text,
			kd.title, kd.content_hash, kd.metadata, kd.status::text,
			coalesce(count(kc.id), 0)::int,
			coalesce(sum(coalesce(kc.token_count, 0)), 0)::int,
			max(kc.embedding_model),
			kd.created_at, kd.updated_at, kd.deleted_at
		from knowledge_docs kd
		left join knowledge_chunks kc on kc.doc_id = kd.id
		where kd.id = $1::uuid and kd.deleted_at is null
		group by kd.id
	`, id))
}

type executor interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
}

func replaceKnowledgeChunks(ctx context.Context, tx executor, docID string, docType string, title string, status string, content string, metadata map[string]any) error {
	return replaceKnowledgeChunkPieces(ctx, tx, docID, docType, title, status, splitText(content, chunkMaxChars, chunkOverlapChars), metadata)
}

func replaceKnowledgeChunkPieces(ctx context.Context, tx executor, docID string, docType string, title string, status string, chunks []string, metadata map[string]any) error {
	if _, err := tx.ExecContext(ctx, `delete from knowledge_chunks where doc_id = $1::uuid`, docID); err != nil {
		return err
	}

	for index, chunk := range chunks {
		chunkMetadata := copyMetadata(metadata)
		chunkMetadata["doc_type"] = docType
		chunkMetadata["status"] = status
		chunkMetadata["title"] = title
		chunkMetadata["chunk_index"] = index
		tokenCount := len(tokenPattern.FindAllString(strings.ToLower(chunk), -1))
		if _, err := tx.ExecContext(ctx, `
			insert into knowledge_chunks
				(doc_id, chunk_index, content, metadata, embedding, embedding_model, token_count)
			values
				($1::uuid, $2, $3, $4::jsonb, $5::vector, $6, $7)
		`, docID, index, chunk, mustJSON(chunkMetadata), vectorLiteral(hashEmbedding(chunk)), embeddingModel, tokenCount); err != nil {
			return err
		}
	}
	return nil
}

func normalizeKnowledgeDocInput(input KnowledgeDocInput) KnowledgeDocInput {
	input.DocType = strings.TrimSpace(input.DocType)
	input.Title = strings.TrimSpace(input.Title)
	input.Content = strings.TrimSpace(input.Content)
	input.Status = normalizeStatus(input.Status)
	if input.Metadata == nil {
		input.Metadata = map[string]any{}
	}
	return input
}

func normalizeKnowledgeDocUpdateInput(input KnowledgeDocUpdateInput) KnowledgeDocUpdateInput {
	input.Title = strings.TrimSpace(input.Title)
	if input.Content != nil {
		content := strings.TrimSpace(*input.Content)
		input.Content = &content
	}
	input.Status = normalizeStatus(input.Status)
	if input.Metadata == nil {
		input.Metadata = map[string]any{}
	}
	return input
}

func normalizeStatus(status string) string {
	status = strings.TrimSpace(status)
	if status == "" {
		return StatusDraft
	}
	return status
}

func validateKnowledgeDocInput(input KnowledgeDocInput) error {
	if _, ok := allowedDocTypes[input.DocType]; !ok {
		return fmt.Errorf("%w: unsupported doc_type", ErrInvalidInput)
	}
	if _, ok := allowedStatuses[input.Status]; !ok {
		return fmt.Errorf("%w: unsupported status", ErrInvalidInput)
	}
	if input.Title == "" || input.Content == "" {
		return fmt.Errorf("%w: title and content are required", ErrInvalidInput)
	}
	return nil
}

func validateKnowledgeDocUpdateInput(input KnowledgeDocUpdateInput) error {
	if _, ok := allowedStatuses[input.Status]; !ok {
		return fmt.Errorf("%w: unsupported status", ErrInvalidInput)
	}
	if input.Title == "" {
		return fmt.Errorf("%w: title is required", ErrInvalidInput)
	}
	if input.Content != nil && *input.Content == "" {
		return fmt.Errorf("%w: content is required when provided", ErrInvalidInput)
	}
	return nil
}

func normalizeKnowledgeDocFilter(filter KnowledgeDocFilter) KnowledgeDocFilter {
	filter.DocType = strings.TrimSpace(filter.DocType)
	filter.Status = strings.TrimSpace(filter.Status)
	filter.Limit = normalizeLimit(filter.Limit, 80)
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizePromptVersionFilter(filter PromptVersionFilter) PromptVersionFilter {
	filter.AgentName = strings.TrimSpace(filter.AgentName)
	filter.Purpose = strings.TrimSpace(filter.Purpose)
	filter.Limit = normalizeLimit(filter.Limit, 80)
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizeReferenceAnswerFilter(filter ReferenceAnswerFilter) ReferenceAnswerFilter {
	filter.Status = strings.TrimSpace(filter.Status)
	filter.Limit = normalizeLimit(filter.Limit, 60)
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizeAdminAuditLogFilter(filter AdminAuditLogFilter) AdminAuditLogFilter {
	filter.Resource = strings.TrimSpace(filter.Resource)
	filter.ActorRole = strings.TrimSpace(filter.ActorRole)
	filter.Method = strings.ToUpper(strings.TrimSpace(filter.Method))
	filter.Query = strings.TrimSpace(filter.Query)
	filter.Limit = normalizeLimit(filter.Limit, 80)
	if filter.StatusClass < 0 || filter.StatusClass > 5 {
		filter.StatusClass = 0
	}
	if filter.Offset < 0 {
		filter.Offset = 0
	}
	return filter
}

func normalizeLimit(value int, fallback int) int {
	if value <= 0 {
		return fallback
	}
	if value > 200 {
		return 200
	}
	return value
}

func knowledgeMetadata(metadata map[string]any, docType string, status string, actorUserID string, indexStatus string) map[string]any {
	next := copyMetadata(metadata)
	next["doc_type"] = docType
	next["status"] = status
	next["source"] = knowledgeSourceAdmin
	next["index_status"] = indexStatus
	next["embedding_model"] = embeddingModel
	next["embedding_dimension"] = embeddingDimension
	next["updated_by"] = actorUserID
	next["updated_at"] = time.Now().UTC().Format(time.RFC3339)
	return next
}

func splitText(content string, maxChars int, overlapChars int) []string {
	content = strings.TrimSpace(content)
	if content == "" {
		return []string{}
	}
	chunks := []string{}
	for start := 0; start < len(content); {
		end := start + maxChars
		if end >= len(content) {
			chunks = append(chunks, strings.TrimSpace(content[start:]))
			break
		}
		cut := end
		if index := strings.LastIndexAny(content[start:end], "\n.?!; "); index > maxChars/2 {
			cut = start + index + 1
		}
		chunks = append(chunks, strings.TrimSpace(content[start:cut]))
		next := cut - overlapChars
		if next <= start {
			next = cut
		}
		start = next
	}
	return chunks
}

func hashContent(content string) string {
	sum := sha256.Sum256([]byte(content))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func hashEmbedding(text string) []float64 {
	vector := make([]float64, embeddingDimension)
	for _, token := range tokenPattern.FindAllString(strings.ToLower(text), -1) {
		hasher, _ := blake2b.New(8, nil)
		_, _ = hasher.Write([]byte(token))
		digest := hasher.Sum(nil)
		index := int(binary.BigEndian.Uint32(digest[:4]) % uint32(embeddingDimension))
		sign := 1.0
		if digest[4]%2 != 0 {
			sign = -1.0
		}
		vector[index] += sign
	}
	norm := 0.0
	for _, value := range vector {
		norm += value * value
	}
	if norm == 0 {
		return vector
	}
	norm = math.Sqrt(norm)
	for index, value := range vector {
		vector[index] = value / norm
	}
	return vector
}

func vectorLiteral(vector []float64) string {
	parts := make([]string, len(vector))
	for index, value := range vector {
		parts[index] = fmt.Sprintf("%.8f", value)
	}
	return "[" + strings.Join(parts, ",") + "]"
}

func marshalMetadata(metadata map[string]any) (string, error) {
	if metadata == nil {
		metadata = map[string]any{}
	}
	payload, err := json.Marshal(metadata)
	if err != nil {
		return "", fmt.Errorf("%w: metadata must be JSON serializable", ErrInvalidInput)
	}
	return string(payload), nil
}

func mustJSON(metadata map[string]any) string {
	payload, err := marshalMetadata(metadata)
	if err != nil {
		return `{}`
	}
	return payload
}

func copyMetadata(metadata map[string]any) map[string]any {
	next := map[string]any{}
	for key, value := range metadata {
		next[key] = value
	}
	return next
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanKnowledgeDoc(row rowScanner) (KnowledgeDoc, error) {
	var doc KnowledgeDoc
	var ownerUserID sql.NullString
	var sourceID sql.NullString
	var metadata []byte
	var embeddingModel sql.NullString
	var deletedAt sql.NullTime
	err := row.Scan(
		&doc.ID,
		&doc.DocType,
		&ownerUserID,
		&sourceID,
		&doc.Title,
		&doc.ContentHash,
		&metadata,
		&doc.Status,
		&doc.ChunkCount,
		&doc.TokenCount,
		&embeddingModel,
		&doc.CreatedAt,
		&doc.UpdatedAt,
		&deletedAt,
	)
	if err != nil {
		return KnowledgeDoc{}, mapError(err)
	}
	doc.OwnerUserID = nullableString(ownerUserID)
	doc.SourceID = nullableString(sourceID)
	doc.Metadata = decodeMap(metadata)
	doc.EmbeddingModel = nullableString(embeddingModel)
	doc.DeletedAt = nullableTime(deletedAt)
	return doc, nil
}

func scanPromptVersion(row rowScanner) (PromptVersion, error) {
	var version PromptVersion
	var metadata []byte
	err := row.Scan(&version.ID, &version.AgentName, &version.Purpose, &version.Version, &version.ContentHash, &metadata, &version.Active, &version.CreatedAt)
	if err != nil {
		return PromptVersion{}, mapError(err)
	}
	version.Metadata = decodeMap(metadata)
	return version, nil
}

func scanReferenceAnswerReview(row rowScanner) (ReferenceAnswerReview, error) {
	var item ReferenceAnswerReview
	var turnID sql.NullString
	var bandTarget sql.NullFloat64
	var skeleton []byte
	var personalizationNotes sql.NullString
	err := row.Scan(&item.ID, &item.ReportID, &turnID, &bandTarget, &skeleton, &item.AnswerText, &personalizationNotes, &item.ReviewStatus, &item.CreatedAt)
	if err != nil {
		return ReferenceAnswerReview{}, mapError(err)
	}
	item.TurnID = nullableString(turnID)
	item.BandTarget = nullableFloat(bandTarget)
	item.Skeleton = decodeMap(skeleton)
	item.PersonalizationNotes = nullableString(personalizationNotes)
	return item, nil
}

func scanAdminAuditLog(row rowScanner) (AdminAuditLog, error) {
	var item AdminAuditLog
	var actorUserID sql.NullString
	var metadata []byte
	err := row.Scan(&item.ID, &actorUserID, &item.ActorRole, &item.Action, &item.Resource, &item.Method, &item.Path, &item.StatusCode, &metadata, &item.CreatedAt)
	if err != nil {
		return AdminAuditLog{}, mapError(err)
	}
	item.ActorUserID = nullableString(actorUserID)
	item.Metadata = decodeMap(metadata)
	return item, nil
}

func decodeMap(payload []byte) map[string]any {
	if len(payload) == 0 {
		return map[string]any{}
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		return map[string]any{}
	}
	if decoded == nil {
		return map[string]any{}
	}
	return decoded
}

func nullableString(value sql.NullString) *string {
	if !value.Valid {
		return nil
	}
	return &value.String
}

func nullableTime(value sql.NullTime) *time.Time {
	if !value.Valid {
		return nil
	}
	return &value.Time
}

func nullableFloat(value sql.NullFloat64) *float64 {
	if !value.Valid {
		return nil
	}
	return &value.Float64
}

func mapError(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	message := err.Error()
	if strings.Contains(message, "invalid input value for enum") || strings.Contains(message, "violates check constraint") {
		return fmt.Errorf("%w: %s", ErrInvalidInput, message)
	}
	return err
}
