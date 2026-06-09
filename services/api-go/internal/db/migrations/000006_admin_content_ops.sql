-- +goose Up

ALTER TABLE reference_answers
    ADD COLUMN review_status content_status NOT NULL DEFAULT 'draft';

CREATE INDEX reference_answers_review_status_idx
    ON reference_answers (review_status, created_at DESC);

INSERT INTO prompt_versions (agent_name, purpose, version, content_hash, metadata, active)
VALUES
    ('ExamWorkflow', 'full_exam_flow', 'mock.exam_workflow.v1', 'sha256:exam-workflow-v1-redacted', '{"seed":"phase8_admin_prompt_catalog_v1","summary":"Controls formal IELTS full exam turn flow and examiner style.","prompt_body_redacted":true,"rollback_from":null}'::jsonb, true),
    ('PracticeWorkflow', 'practice_flow', 'mock.practice_workflow.v1', 'sha256:practice-workflow-v1-redacted', '{"seed":"phase8_admin_prompt_catalog_v1","summary":"Controls part and topic practice flow with coach-style hints.","prompt_body_redacted":true,"rollback_from":null}'::jsonb, true),
    ('FollowupPlannerAgent', 'followup_planning', 'mock.followup_planner.v1', 'sha256:followup-planner-v1-redacted', '{"seed":"phase8_admin_prompt_catalog_v1","summary":"Plans privacy-aware follow-up questions from ASR answers.","prompt_body_redacted":true,"rollback_from":null}'::jsonb, true),
    ('ScoringWorkflow', 'ielts_scoring', 'scoring.workflow.v1', 'sha256:scoring-workflow-v1-redacted', '{"seed":"phase8_admin_prompt_catalog_v1","summary":"Coordinates criterion scorers, reviewer, calibrator and report output.","prompt_body_redacted":true,"rollback_from":null}'::jsonb, true),
    ('FeedbackCoachAgent', 'feedback_generation', 'feedback.coach.v1', 'sha256:feedback-coach-v1-redacted', '{"seed":"phase8_admin_prompt_catalog_v1","summary":"Generates learner-facing feedback, reference answers and study plan items.","prompt_body_redacted":true,"rollback_from":null}'::jsonb, true)
ON CONFLICT (agent_name, purpose, version) DO NOTHING;

-- +goose Down

DELETE FROM prompt_versions
WHERE metadata->>'seed' = 'phase8_admin_prompt_catalog_v1';

DROP INDEX IF EXISTS reference_answers_review_status_idx;

ALTER TABLE reference_answers
    DROP COLUMN IF EXISTS review_status;
