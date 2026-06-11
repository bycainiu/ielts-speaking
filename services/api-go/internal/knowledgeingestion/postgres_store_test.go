package knowledgeingestion

import "testing"

func TestBackgroundFactsFromCandidateSupportsAgentSingleFactPayload(t *testing.T) {
	candidate := KnowledgeIngestionCandidate{
		CandidateKind: CandidateKindBackground,
		NormalizedPayload: map[string]any{
			"topic":         "learning_goal",
			"fact_key":      "weakness",
			"fact_value":    "fluency drops on abstract topics",
			"privacy_level": "normal",
			"allowed_usage": []any{"question_personalization", "feedback_personalization"},
		},
	}

	facts := backgroundFactsFromCandidate(candidate)
	if len(facts) != 1 {
		t.Fatalf("facts length = %d, want 1", len(facts))
	}
	if facts[0].Topic == nil || *facts[0].Topic != "learning_goal" {
		t.Fatalf("topic = %v, want learning_goal", facts[0].Topic)
	}
	if facts[0].FactKey != "weakness" {
		t.Fatalf("fact key = %q, want weakness", facts[0].FactKey)
	}
	if facts[0].FactValue != "fluency drops on abstract topics" {
		t.Fatalf("fact value = %q", facts[0].FactValue)
	}
	if len(facts[0].AllowedUsage) != 2 {
		t.Fatalf("allowed usage length = %d, want 2", len(facts[0].AllowedUsage))
	}
}

func TestBackgroundFactsFromCandidateSupportsBatchFactsPayload(t *testing.T) {
	candidate := KnowledgeIngestionCandidate{
		CandidateKind: CandidateKindBackground,
		NormalizedPayload: map[string]any{
			"facts": []any{
				map[string]any{
					"topic":      "personal_profile",
					"fact_key":   "city",
					"fact_value": "Hangzhou",
				},
				map[string]any{
					"topic":      "learning_goal",
					"fact_key":   "target_band",
					"fact_value": "7.5",
				},
			},
		},
	}

	facts := backgroundFactsFromCandidate(candidate)
	if len(facts) != 2 {
		t.Fatalf("facts length = %d, want 2", len(facts))
	}
	if facts[0].PrivacyLevel != "normal" {
		t.Fatalf("default privacy level = %q, want normal", facts[0].PrivacyLevel)
	}
	if got := facts[1].FactKey; got != "target_band" {
		t.Fatalf("second fact key = %q, want target_band", got)
	}
}
