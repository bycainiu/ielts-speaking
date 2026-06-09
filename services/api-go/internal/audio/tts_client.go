package audio

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"
)

type TTSProvider interface {
	Synthesize(ctx context.Context, request TTSProviderRequest) (TTSProviderResponse, error)
}

type AgentHarnessTTSClient struct {
	baseURL    string
	httpClient *http.Client
}

func NewAgentHarnessTTSClient(baseURL string) AgentHarnessTTSClient {
	return AgentHarnessTTSClient{
		baseURL: strings.TrimRight(baseURL, "/"),
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c AgentHarnessTTSClient) Synthesize(ctx context.Context, request TTSProviderRequest) (TTSProviderResponse, error) {
	payload, err := json.Marshal(request)
	if err != nil {
		return TTSProviderResponse{}, err
	}
	httpRequest, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/agent/audio/synthesize", bytes.NewReader(payload))
	if err != nil {
		return TTSProviderResponse{}, err
	}
	httpRequest.Header.Set("Content-Type", "application/json")

	response, err := c.httpClient.Do(httpRequest)
	if err != nil {
		return TTSProviderResponse{}, err
	}
	defer response.Body.Close()

	if response.StatusCode >= 400 {
		return TTSProviderResponse{}, fmt.Errorf("agent harness tts returned %s", response.Status)
	}

	var result TTSProviderResponse
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return TTSProviderResponse{}, err
	}
	return result, nil
}
