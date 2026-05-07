-- AutoPilot Queue Persistence — DDL only (additive, no drops)
-- Applied manually because dev.db has no migration history baseline yet

CREATE TABLE IF NOT EXISTS "AutoPilotQueueRecord" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "projectId" TEXT NOT NULL,
    "featureId" TEXT,
    "status" TEXT NOT NULL,
    "currentIndex" INTEGER NOT NULL DEFAULT 0,
    "pauseReason" TEXT,
    "resetTime" DATETIME,
    "config" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    "completedAt" DATETIME,
    CONSTRAINT "AutoPilotQueueRecord_projectId_fkey" FOREIGN KEY ("projectId") REFERENCES "Project" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS "AutoPilotTaskRecord" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "queueId" TEXT NOT NULL,
    "sequence" INTEGER NOT NULL,
    "issueId" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "sessionId" TEXT,
    "startedAt" DATETIME,
    "completedAt" DATETIME,
    "failureReason" TEXT,
    CONSTRAINT "AutoPilotTaskRecord_queueId_fkey" FOREIGN KEY ("queueId") REFERENCES "AutoPilotQueueRecord" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS "AutoPilotEvent" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "queueId" TEXT NOT NULL,
    "type" TEXT NOT NULL,
    "payload" TEXT NOT NULL,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "AutoPilotEvent_queueId_fkey" FOREIGN KEY ("queueId") REFERENCES "AutoPilotQueueRecord" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS "AutoPilotQueueRecord_projectId_status_idx" ON "AutoPilotQueueRecord"("projectId", "status");
CREATE INDEX IF NOT EXISTS "AutoPilotQueueRecord_status_idx" ON "AutoPilotQueueRecord"("status");
CREATE INDEX IF NOT EXISTS "AutoPilotTaskRecord_queueId_sequence_idx" ON "AutoPilotTaskRecord"("queueId", "sequence");
CREATE INDEX IF NOT EXISTS "AutoPilotTaskRecord_issueId_idx" ON "AutoPilotTaskRecord"("issueId");
CREATE INDEX IF NOT EXISTS "AutoPilotEvent_queueId_createdAt_idx" ON "AutoPilotEvent"("queueId", "createdAt");
CREATE INDEX IF NOT EXISTS "AutoPilotEvent_type_createdAt_idx" ON "AutoPilotEvent"("type", "createdAt");
