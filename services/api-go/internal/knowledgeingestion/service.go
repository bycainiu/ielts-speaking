package knowledgeingestion

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"path/filepath"
	"strings"
	"time"
)

const defaultMaxUploadBytes int64 = 20 * 1024 * 1024

func NewService(store Store, objects ObjectStore, bucket string, maxBytes int64) Service {
	if maxBytes <= 0 {
		maxBytes = defaultMaxUploadBytes
	}
	return Service{
		store:    store,
		objects:  objects,
		bucket:   bucket,
		maxBytes: maxBytes,
	}
}

func (s Service) Upload(ctx context.Context, input CreateUploadInput) (KnowledgeImportJobDetail, error) {
	input = normalizeCreateUploadInput(input)
	if err := s.validateCreateUploadInput(input); err != nil {
		return KnowledgeImportJobDetail{}, err
	}

	if _, err := input.Content.Seek(0, io.SeekStart); err != nil {
		return KnowledgeImportJobDetail{}, fmt.Errorf("%w: %v", ErrInvalidInput, err)
	}

	if err := s.objects.EnsureBucket(ctx, s.bucket); err != nil {
		return KnowledgeImportJobDetail{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
	}

	checksum := sha256.New()
	key := objectKey(input.UserID, input.FileName)
	reader := io.TeeReader(input.Content, checksum)
	if err := s.objects.PutObject(ctx, s.bucket, key, reader, input.SizeBytes, input.MimeType); err != nil {
		return KnowledgeImportJobDetail{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
	}

	if _, err := input.Content.Seek(0, io.SeekStart); err != nil {
		return KnowledgeImportJobDetail{}, fmt.Errorf("%w: %v", ErrInvalidInput, err)
	}

	return s.store.CreateUpload(ctx, CreateUploadRecordInput{
		OwnerUserID:     input.UserID,
		Visibility:      input.Visibility,
		Purpose:         input.Purpose,
		Title:           resolveTitle(input.Title, input.FileName),
		OriginalFile:    input.FileName,
		Extension:       normalizedExtension(input.FileName),
		MimeType:        input.MimeType,
		SizeBytes:       input.SizeBytes,
		ChecksumSHA256:  hex.EncodeToString(checksum.Sum(nil)),
		StorageBucket:   s.bucket,
		StorageKey:      key,
		SourceMetadata:  map[string]any{"uploaded_via": "api_go"},
		RequestedAction: input.Purpose,
	})
}

func (s Service) ListUserJobs(ctx context.Context, userID string, filter UserJobFilter) ([]KnowledgeImportJobSummary, error) {
	return s.store.ListUserJobs(ctx, userID, filter)
}

func (s Service) ListAdminJobs(ctx context.Context, filter AdminJobFilter) ([]KnowledgeImportJobSummary, error) {
	return s.store.ListAdminJobs(ctx, filter)
}

func (s Service) GetJobDetail(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error) {
	detail, err := s.store.GetJobDetail(ctx, jobID)
	if err != nil {
		return KnowledgeImportJobDetail{}, err
	}
	if requesterRole == "operator" || requesterRole == "admin" || detail.OwnerUserID == requesterUserID {
		return detail, nil
	}
	return KnowledgeImportJobDetail{}, ErrForbidden
}

func (s Service) ConfirmBackgroundCandidates(ctx context.Context, userID string, jobID string, input ConfirmBackgroundInput) (KnowledgeImportJobDetail, error) {
	return s.store.ConfirmBackgroundCandidates(ctx, userID, jobID, input)
}

func (s Service) ReviewJob(ctx context.Context, reviewerUserID string, reviewerRole string, jobID string, input AdminReviewInput) (KnowledgeImportJobDetail, error) {
	return s.store.ReviewJob(ctx, reviewerUserID, reviewerRole, jobID, input)
}

func (s Service) CancelJob(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error) {
	return s.store.CancelJob(ctx, requesterUserID, requesterRole, jobID)
}

func (s Service) RetryJob(ctx context.Context, requesterUserID string, requesterRole string, jobID string) (KnowledgeImportJobDetail, error) {
	return s.store.RetryJob(ctx, requesterUserID, requesterRole, jobID)
}

func (s Service) GetRuntimePolicy(ctx context.Context) (RuntimePolicy, error) {
	return s.store.GetRuntimePolicy(ctx)
}

func (s Service) UpdateRuntimePolicy(ctx context.Context, actorUserID string, input RuntimePolicyUpdateInput) (RuntimePolicy, error) {
	return s.store.UpdateRuntimePolicy(ctx, actorUserID, input)
}

func (s Service) PreviewArtifact(ctx context.Context, requesterUserID string, requesterRole string, jobID string, artifactID string, publicHostname string) (ArtifactPreview, error) {
	detail, err := s.GetJobDetail(ctx, requesterUserID, requesterRole, jobID)
	if err != nil {
		return ArtifactPreview{}, err
	}
	for _, artifact := range detail.Artifacts {
		if artifact.ID != artifactID {
			continue
		}
		preview := ArtifactPreview{Artifact: artifact}
		if artifact.StorageBucket != nil && artifact.StorageKey != nil {
			url, err := s.objects.PresignedGetObject(ctx, *artifact.StorageBucket, *artifact.StorageKey, 10*time.Minute, publicHostname)
			if err != nil {
				return ArtifactPreview{}, fmt.Errorf("%w: %v", ErrStorageUnavailable, err)
			}
			preview.SignedURL = &url
		}
		return preview, nil
	}
	return ArtifactPreview{}, ErrNotFound
}

func normalizeCreateUploadInput(input CreateUploadInput) CreateUploadInput {
	input.Visibility = strings.TrimSpace(strings.ToLower(input.Visibility))
	input.Purpose = strings.TrimSpace(strings.ToLower(input.Purpose))
	input.Title = strings.TrimSpace(input.Title)
	input.FileName = strings.TrimSpace(input.FileName)
	input.MimeType = strings.ToLower(strings.TrimSpace(strings.Split(input.MimeType, ";")[0]))
	if input.Visibility == "" {
		input.Visibility = VisibilityPrivate
	}
	if input.Purpose == "" {
		input.Purpose = PurposeAuto
	}
	if input.MimeType == "" || input.MimeType == "application/octet-stream" {
		input.MimeType = mimeTypeFromExtension(normalizedExtension(input.FileName))
	}
	return input
}

func (s Service) validateCreateUploadInput(input CreateUploadInput) error {
	if input.UserID == "" || input.FileName == "" || input.SizeBytes <= 0 || input.Content == nil {
		return ErrInvalidInput
	}
	if input.SizeBytes > s.maxBytes {
		return ErrFileTooLarge
	}
	switch input.Visibility {
	case VisibilityPrivate, VisibilityPublic:
	default:
		return ErrInvalidInput
	}
	switch input.Purpose {
	case PurposeAuto, PurposeQuestionBank, PurposeKnowledge, PurposeBackground, PurposeMixed:
	default:
		return ErrInvalidInput
	}
	ext := normalizedExtension(input.FileName)
	if ext == "" {
		return ErrUnsupportedType
	}
	mime := input.MimeType
	allowedMIME, ok := allowedExtensions()[ext]
	if !ok {
		return ErrUnsupportedType
	}
	if mime == "" {
		return ErrUnsupportedType
	}
	for _, candidate := range allowedMIME {
		if candidate == mime {
			return nil
		}
	}
	return ErrUnsupportedType
}

func allowedExtensions() map[string][]string {
	return map[string][]string{
		".md":       {"text/markdown", "text/plain"},
		".markdown": {"text/markdown", "text/plain"},
		".txt":      {"text/plain"},
		".pdf":      {"application/pdf"},
		".docx":     {"application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
	}
}

func mimeTypeFromExtension(ext string) string {
	switch ext {
	case ".md", ".markdown":
		return "text/markdown"
	case ".txt":
		return "text/plain"
	case ".pdf":
		return "application/pdf"
	case ".docx":
		return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
	default:
		return ""
	}
}

func normalizedExtension(name string) string {
	return strings.ToLower(strings.TrimSpace(filepath.Ext(name)))
}

func resolveTitle(title string, fileName string) string {
	if title != "" {
		return title
	}
	base := strings.TrimSpace(strings.TrimSuffix(fileName, filepath.Ext(fileName)))
	if base == "" {
		return "Uploaded knowledge document"
	}
	return base
}

func objectKey(userID string, fileName string) string {
	ext := normalizedExtension(fileName)
	stem := strings.TrimSuffix(filepath.Base(fileName), filepath.Ext(fileName))
	stem = strings.ReplaceAll(stem, " ", "-")
	stem = strings.ReplaceAll(stem, "_", "-")
	stem = strings.ToLower(strings.Trim(stem, "-"))
	if stem == "" {
		stem = "document"
	}
	return fmt.Sprintf("knowledge/%s/%s/%d-%s%s", userID, time.Now().UTC().Format("20060102"), time.Now().UTC().UnixNano(), stem, ext)
}
