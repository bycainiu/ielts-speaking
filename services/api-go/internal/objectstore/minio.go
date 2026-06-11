package objectstore

import (
	"context"
	"io"
	"net"
	"net/url"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
)

type ObjectStore interface {
	EnsureBucket(ctx context.Context, bucket string) error
	PutObject(ctx context.Context, bucket string, key string, content io.Reader, size int64, contentType string) error
	PresignedGetObject(ctx context.Context, bucket string, key string, expires time.Duration, publicHostname string) (string, error)
}

type MinIOObjectStore struct {
	client         *minio.Client
	presignClient  *minio.Client
	region         string
	endpoint       string
	publicEndpoint string
	accessKey      string
	secretKey      string
	useSSL         bool
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

	return MinIOObjectStore{
		client:         client,
		presignClient:  presignClient,
		region:         cfg.Region,
		endpoint:       cfg.Endpoint,
		publicEndpoint: cfg.PublicEndpoint,
		accessKey:      cfg.AccessKey,
		secretKey:      cfg.SecretKey,
		useSSL:         cfg.UseSSL,
	}, nil
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

func (s MinIOObjectStore) PresignedGetObject(ctx context.Context, bucket string, key string, expires time.Duration, publicHostname string) (string, error) {
	presignClient, err := s.presignClientForHostname(publicHostname)
	if err != nil {
		return "", err
	}
	u, err := presignClient.PresignedGetObject(ctx, bucket, key, expires, url.Values{})
	if err != nil {
		return "", err
	}
	return u.String(), nil
}

func (s MinIOObjectStore) presignClientForHostname(publicHostname string) (*minio.Client, error) {
	publicHostname = strings.Trim(strings.ToLower(strings.TrimSpace(publicHostname)), "[]")
	if publicHostname == "" {
		return s.presignClient, nil
	}

	baseEndpoint := strings.TrimSpace(s.publicEndpoint)
	if baseEndpoint == "" {
		baseEndpoint = strings.TrimSpace(s.endpoint)
	}
	normalizedBase, secure := normalizeEndpoint(baseEndpoint, s.useSSL)
	baseHostname, err := HostnameFromValue(normalizedBase)
	if err != nil || baseHostname == "" {
		return s.presignClient, nil
	}
	if !ShouldRewritePlaybackHost(baseHostname) || baseHostname == publicHostname {
		return s.presignClient, nil
	}

	overrideEndpoint, err := replaceEndpointHostname(normalizedBase, publicHostname)
	if err != nil {
		return nil, err
	}
	return minio.New(overrideEndpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(s.accessKey, s.secretKey, ""),
		Secure: secure,
		Region: s.region,
	})
}

func replaceEndpointHostname(endpoint string, hostname string) (string, error) {
	parsed, err := url.Parse("http://" + strings.TrimSpace(endpoint))
	if err != nil {
		return "", err
	}
	if port := parsed.Port(); port != "" {
		return net.JoinHostPort(hostname, port), nil
	}
	return hostname, nil
}

func NormalizeEndpoint(endpoint string, useSSL bool) (string, bool) {
	endpoint = strings.TrimSpace(endpoint)
	if strings.HasPrefix(endpoint, "http://") {
		return strings.TrimPrefix(endpoint, "http://"), false
	}
	if strings.HasPrefix(endpoint, "https://") {
		return strings.TrimPrefix(endpoint, "https://"), true
	}
	return endpoint, useSSL
}

func normalizeEndpoint(endpoint string, useSSL bool) (string, bool) {
	return NormalizeEndpoint(endpoint, useSSL)
}

func HostnameFromValue(value string) (string, error) {
	normalized := strings.TrimSpace(value)
	if normalized == "" {
		return "", nil
	}
	if !strings.Contains(normalized, "://") {
		normalized = "http://" + normalized
	}
	parsed, err := url.Parse(normalized)
	if err != nil {
		return "", err
	}
	hostname := strings.TrimSpace(parsed.Hostname())
	if hostname == "" {
		return "", nil
	}
	return strings.Trim(strings.ToLower(hostname), "[]"), nil
}

func ShouldRewritePlaybackHost(hostname string) bool {
	normalized := strings.Trim(strings.ToLower(strings.TrimSpace(hostname)), "[]")
	if normalized == "" {
		return false
	}
	if IsLoopbackHostname(normalized) {
		return true
	}
	if normalized == "minio" {
		return true
	}
	return !strings.Contains(normalized, ".") && net.ParseIP(normalized) == nil
}

func IsLoopbackHostname(hostname string) bool {
	return hostname == "localhost" || hostname == "127.0.0.1" || hostname == "::1"
}
