"""users, api_keys, channel_links, channel_pairing_codes

Revision ID: 0003_users_and_api_keys
Revises: 0002_onboarding_tokens
Create Date: 2026-05-06
"""

from alembic import op

revision = "0003_users_and_api_keys"
down_revision = "0002_onboarding_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            timezone TEXT NOT NULL DEFAULT 'UTC',
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_login_at TIMESTAMPTZ
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            key_hash TEXT UNIQUE NOT NULL,
            prefix TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            last_used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_user ON api_keys(user_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash) WHERE revoked_at IS NULL;"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            external_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(channel, external_id)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_channel_links_user ON channel_links(user_id);")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS channel_pairing_codes (
            code TEXT PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL,
            redeemed_at TIMESTAMPTZ
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pairing_codes_expires ON channel_pairing_codes(expires_at);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_pairing_codes;")
    op.execute("DROP TABLE IF EXISTS channel_links;")
    op.execute("DROP TABLE IF EXISTS api_keys;")
    op.execute("DROP TABLE IF EXISTS users;")
