"""platform schema

Revision ID: 0001_platform_schema
Revises:
Create Date: 2026-04-20
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0001_platform_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector";')

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            external_id TEXT UNIQUE NOT NULL,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_active_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            session_key TEXT NOT NULL,
            messages JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            last_consolidated INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(tenant_id, session_key)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            key TEXT NOT NULL,
            content TEXT NOT NULL,
            version INT NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(tenant_id, key)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS memory_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            summary TEXT,
            embedding vector(1536),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_memory_history_tenant ON memory_history(tenant_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS checkpoints (
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            session_key TEXT NOT NULL,
            state JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, session_key)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cron_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            schedule TEXT NOT NULL,
            payload JSONB NOT NULL,
            next_run_at TIMESTAMPTZ NOT NULL,
            last_run_at TIMESTAMPTZ,
            enabled BOOLEAN NOT NULL DEFAULT true
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_cron_jobs_next_run ON cron_jobs(next_run_at) WHERE enabled = true;")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            session_key TEXT,
            model TEXT,
            total_tokens INT,
            total_cost NUMERIC(10,6),
            latency_ms INT,
            tool_calls INT,
            success BOOLEAN,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_created_at ON agent_runs(created_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS agent_runs;")
    op.execute("DROP TABLE IF EXISTS cron_jobs;")
    op.execute("DROP TABLE IF EXISTS checkpoints;")
    op.execute("DROP TABLE IF EXISTS memory_history;")
    op.execute("DROP TABLE IF EXISTS memory_documents;")
    op.execute("DROP TABLE IF EXISTS sessions;")
    op.execute("DROP TABLE IF EXISTS tenants;")

