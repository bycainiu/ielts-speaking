package questionbank

import (
	"errors"
	"testing"
)

func TestIsPlaceholderQuestionText(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		text string
		want bool
	}{
		{name: "plain chinese placeholder", text: "待补充", want: true},
		{name: "numbered placeholder", text: "5. 待补充", want: true},
		{name: "english placeholder", text: "TODO: add follow-up", want: true},
		{name: "real question", text: "Why do some people enjoy travelling alone?", want: false},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			if got := isPlaceholderQuestionText(tc.text); got != tc.want {
				t.Fatalf("isPlaceholderQuestionText(%q) = %v, want %v", tc.text, got, tc.want)
			}
		})
	}
}

func TestValidateQuestionInputRejectsPlaceholderText(t *testing.T) {
	t.Parallel()

	err := validateQuestionInput(QuestionInput{
		Part: 1,
		Text: "待补充",
	})
	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("validateQuestionInput() error = %v, want ErrInvalidInput", err)
	}
}

func TestValidateQuestionInputRejectsPlaceholderFollowup(t *testing.T) {
	t.Parallel()

	err := validateQuestionInput(QuestionInput{
		Part: 2,
		Text: "Describe a meal you enjoyed with your family.",
		CueCard: &CueCardInput{
			Prompt:             "Describe a meal you enjoyed with your family.",
			BulletPoints:       []string{"what it was"},
			PreparationSeconds: 60,
			SpeakingSeconds:    120,
		},
		Followups: []FollowupTemplateInput{
			{Part: 3, Text: "待补充"},
		},
	})
	if !errors.Is(err, ErrInvalidInput) {
		t.Fatalf("validateQuestionInput() error = %v, want ErrInvalidInput", err)
	}
}
