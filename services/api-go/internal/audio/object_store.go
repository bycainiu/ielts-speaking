package audio

import "github.com/ielts-speaking/platform/services/api-go/internal/objectstore"

type ObjectStore = objectstore.ObjectStore
type MinIOObjectStore = objectstore.MinIOObjectStore
type MinIOConfig = objectstore.MinIOConfig

var NewMinIOObjectStore = objectstore.NewMinIOObjectStore

func normalizeEndpoint(endpoint string, useSSL bool) (string, bool) {
	return objectstore.NormalizeEndpoint(endpoint, useSSL)
}
