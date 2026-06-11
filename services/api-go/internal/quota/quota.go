package quota

import (
	"errors"
	"fmt"
)

var (
	ErrQuotaExceeded       = errors.New("quota: exceeded")
	ErrSubscriptionExpired = errors.New("quota: subscription expired")
)

const (
	ModeFullExam      = "full_exam"
	ModePartPractice  = "part_practice"
	ModeTopicPractice = "topic_practice"
)

type ExceededDetails struct {
	Required  int
	Remaining int
	PlanSlug  string
}

func CreditWeight(mode string) int {
	switch mode {
	case ModeFullExam:
		return 3
	case ModePartPractice, ModeTopicPractice:
		return 1
	default:
		return 1
	}
}

func IsPrivilegedRole(role string) bool {
	return role == "operator" || role == "admin"
}

func Exceeded(required, remaining int, planSlug string) error {
	return fmt.Errorf("%w: required=%d remaining=%d plan=%s", ErrQuotaExceeded, required, remaining, planSlug)
}

func ExceededDetailsFrom(err error) (ExceededDetails, bool) {
	if !errors.Is(err, ErrQuotaExceeded) {
		return ExceededDetails{}, false
	}
	var required, remaining int
	var planSlug string
	_, parseErr := fmt.Sscanf(err.Error(), "quota: exceeded: required=%d remaining=%d plan=%s", &required, &remaining, &planSlug)
	if parseErr != nil {
		return ExceededDetails{}, true
	}
	return ExceededDetails{Required: required, Remaining: remaining, PlanSlug: planSlug}, true
}
