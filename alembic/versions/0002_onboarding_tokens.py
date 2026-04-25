"""onboarding tokens + onboarding state

Revision ID: 0002_onboarding_tokens
Revises: 0001_platform_schema
Create Date: 2026-04-20
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0002_onboarding_tokens"
down_revision = "0001_platform_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            token_hash TEXT UNIQUE NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            redeemed_at TIMESTAMPTZ,
            redeemed_channel TEXT,
            redeemed_chat_id TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_onboarding_tokens_expires_at ON onboarding_tokens(expires_at);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_onboarding_tokens_redeemed_at ON onboarding_tokens(redeemed_at);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS onboarding_state (
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            session_key TEXT NOT NULL,
            status TEXT NOT NULL,
            phase TEXT NOT NULL,
            draft_submission JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, session_key)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_onboarding_state_status ON onboarding_state(status);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS onboarding_state;")
    op.execute("DROP TABLE IF EXISTS onboarding_tokens;")

