package quota

import "testing"

func TestCreditWeight(t *testing.T) {
	tests := []struct {
		mode string
		want int
	}{
		{ModeFullExam, 3},
		{ModePartPractice, 1},
		{ModeTopicPractice, 1},
		{"unknown", 1},
	}
	for _, tt := range tests {
		if got := CreditWeight(tt.mode); got != tt.want {
			t.Fatalf("CreditWeight(%q) = %d, want %d", tt.mode, got, tt.want)
		}
	}
}

func TestExceededDetailsFrom(t *testing.T) {
	err := Exceeded(3, 1, "free")
	details, ok := ExceededDetailsFrom(err)
	if !ok {
		t.Fatal("expected details")
	}
	if details.Required != 3 || details.Remaining != 1 || details.PlanSlug != "free" {
		t.Fatalf("unexpected details: %+v", details)
	}
}

func TestIsPrivilegedRole(t *testing.T) {
	if !IsPrivilegedRole("admin") || !IsPrivilegedRole("operator") {
		t.Fatal("expected privileged roles")
	}
	if IsPrivilegedRole("user") {
		t.Fatal("user should not be privileged")
	}
}
