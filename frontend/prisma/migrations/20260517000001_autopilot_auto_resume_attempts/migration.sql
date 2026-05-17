-- CB-2794: Persist auto_resume_attempts to DB so the circuit breaker survives
-- backend restarts that occur during a waiting_reset state.
ALTER TABLE "AutoPilotQueueRecord" ADD COLUMN "autoResumeAttempts" INTEGER NOT NULL DEFAULT 0;
