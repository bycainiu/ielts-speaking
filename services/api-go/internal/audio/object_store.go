package audio

import (
	"context"
	"io"
	"net/url"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type ObjectStore interface {
	EnsureBucket(ctx context.Context, bucket string) error
	PutObject(ctx context.Context, bucket string, key string, content io.Reader, size int64, contentType string) error
	PresignedGetObject(ctx context.Context, bucket string, key string, expires time.Duration) (string, error)
}

type MinIOObjectStore struct {
	client        *minio.Client
	presignClient *minio.Client
	region        string
}

type MinIOConfig struct {
	Endpoint       string
	PublicEndpoint string
	AccessKey      string
	SecretKey      string
	Region         string
	UseSSL         bool
}

func NewMinIOObjectStore(cfg MinIOConfig) (MinIOObjectStore, error) {
	endpoint, secure := normalizeEndpoint(cfg.Endpoint, cfg.UseSSL)
	client, err := minio.New(endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
		Secure: secure,
		Region: cfg.Region,
	})
	if err != nil {
		return MinIOObjectStore{}, err
	}

	presignClient := client
	if strings.TrimSpace(cfg.PublicEndpoint) != "" {
		publicEndpoint, publicSecure := normalizeEndpoint(cfg.PublicEndpoint, cfg.UseSSL)
		presignClient, err = minio.New(publicEndpoint, &minio.Options{
			Creds:  credentials.NewStaticV4(cfg.AccessKey, cfg.SecretKey, ""),
			Secure: publicSecure,
			Region: cfg.Region,
		})
		if err != nil {
			return MinIOObjectStore{}, err
		}
	}

	return MinIOObjectStore{client: client, presignClient: presignClient, region: cfg.Region}, nil
}

func (s MinIOObjectStore) EnsureBucket(ctx context.Context, bucket string) error {
	exists, err := s.client.BucketExists(ctx, bucket)
	if err != nil {
		return err
	}
	if exists {
		return nil
	}
	return s.client.MakeBucket(ctx, bucket, minio.MakeBucketOptions{Region: s.region})
}

func (s MinIOObjectStore) PutObject(ctx context.Context, bucket string, key string, content io.Reader, size int64, contentType string) error {
	_, err := s.client.PutObject(ctx, bucket, key, content, size, minio.PutObjectOptions{ContentType: contentType})
	return err
}

func (s MinIOObjectStore) PresignedGetObject(ctx context.Context, bucket string, key string, expires time.Duration) (string, error) {
	u, err := s.presignClient.PresignedGetObject(ctx, bucket, key, expires, url.Values{})
	if err != nil {
		return "", err
	}
	return u.String(), nil
}

func normalizeEndpoint(endpoint string, useSSL bool) (string, bool) {
	endpoint = strings.TrimSpace(endpoint)
	if strings.HasPrefix(endpoint, "http://") {
		return strings.TrimPrefix(endpoint, "http://"), false
	}
	if strings.HasPrefix(endpoint, "https://") {
		return strings.TrimPrefix(endpoint, "https://"), true
	}
	return endpoint, useSSL
}
