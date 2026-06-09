package audio

import (
	"testing"
)

func TestNormalizeEndpointReadsScheme(t *testing.T) {
	endpoint, secure := normalizeEndpoint("http://localhost:9000", true)
	if endpoint != "localhost:9000" {
		t.Fatalf("endpoint = %q, want localhost:9000", endpoint)
	}
	if secure {
		t.Fatal("secure = true, want false for http endpoint")
	}
}

func TestNormalizeEndpointKeepsFallbackSSL(t *testing.T) {
	endpoint, secure := normalizeEndpoint("minio:9000", true)
	if endpoint != "minio:9000" {
		t.Fatalf("endpoint = %q, want minio:9000", endpoint)
	}
	if !secure {
		t.Fatal("secure = false, want true from fallback")
	}
}
