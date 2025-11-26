"""add auth billing usage tables

Revision ID: 202501010900
Revises: None (initial migration)
Create Date: 2025-01-01 09:00:00.000000

This migration creates the core tables for:
- Users (mirrors Supabase auth with Stripe linkage)
- Subscriptions (current subscription state per user)
- Usage Counters (aggregated per billing period)
- Usage Events (append-only audit log)
- Jobs (enhanced with user context and correlation tracking)

All tables follow the schema defined in:
- docs/Production Database Migration & Schema Versioning.txt
- docs/Operational Readiness & Production Hardening Plan.txt
- ADR-0005: Database Schema Strategy
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# Revision identifiers, used by Alembic
revision = '202501010900'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure citext extension for case-insensitive emails
    op.execute('CREATE EXTENSION IF NOT EXISTS citext')

    # =========================================================================
    # Users table - mirrors Supabase auth users with Stripe linkage
    # =========================================================================
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', postgresql.CITEXT(), nullable=False),
        sa.Column('stripe_customer_id', sa.Text(), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('users_email_idx', 'users', ['email'], unique=True)

    # =========================================================================
    # Subscriptions - current subscription state per user
    # =========================================================================
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stripe_subscription_id', sa.Text(), nullable=False),
        sa.Column('plan', sa.Text(), nullable=False),  # 'FREE', 'PRO', 'ENTERPRISE'
        sa.Column('status', sa.Text(), nullable=False),  # 'active', 'past_due', etc.
        sa.Column('current_period_start', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('current_period_end', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('stripe_subscription_id'),
    )
    op.create_index('subscriptions_user_id_idx', 'subscriptions', ['user_id'])
    op.create_index('subscriptions_status_idx', 'subscriptions', ['status'])

    # =========================================================================
    # Usage counters - aggregated usage per billing period
    # =========================================================================
    op.create_table(
        'usage_counters',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('period_start', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('period_end', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('jobs_used', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('jobs_limit', sa.Integer(), nullable=True),
        sa.Column('credits_remaining', sa.Integer(), nullable=True),
        sa.Column('last_reconciled_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('usage_counters_user_idx', 'usage_counters', ['user_id'])
    op.create_unique_constraint(
        'usage_counters_user_period_uniq',
        'usage_counters',
        ['user_id', 'period_start', 'period_end'],
    )

    # =========================================================================
    # Usage events - append-only audit log for all usage changes
    # =========================================================================
    op.create_table(
        'usage_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False),  # 'job_run', 'credit_change', etc.
        sa.Column('amount', sa.Integer(), nullable=False),  # +1 job, -1 credit, etc.
        sa.Column('job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('stripe_event_id', sa.Text(), nullable=True),
        sa.Column(
            'metadata',
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column('occurred_at', postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('usage_events_user_time_idx', 'usage_events', ['user_id', 'occurred_at'])
    # Partial unique index for Stripe event idempotency
    op.create_index(
        'usage_events_stripe_event_id_idx',
        'usage_events',
        ['stripe_event_id'],
        unique=True,
        postgresql_where=sa.text('stripe_event_id IS NOT NULL'),
    )

    # =========================================================================
    # Jobs table - core job entity (may already exist, so we add columns)
    # =========================================================================
    # First, create the table if it doesn't exist
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('correlation_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='PENDING'),
        sa.Column(
            'payload',
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('next_run_at', postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('idempotency_key', sa.String(128), nullable=True),
        sa.Column(
            'created_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('idempotency_key'),
    )

    # Create indexes for jobs table
    op.create_index('jobs_status_idx', 'jobs', ['status'])
    op.create_index('jobs_user_id_idx', 'jobs', ['user_id'])
    op.create_index('jobs_user_created_at_idx', 'jobs', ['user_id', 'created_at'])
    op.create_index('jobs_user_status_idx', 'jobs', ['user_id', 'status'])
    op.create_index('jobs_correlation_id_idx', 'jobs', ['correlation_id'])
    op.create_index('jobs_status_next_run_at_idx', 'jobs', ['status', 'next_run_at'])
    op.create_index('jobs_idempotency_key_idx', 'jobs', ['idempotency_key'])
    op.create_index('jobs_next_run_at_idx', 'jobs', ['next_run_at'])


def downgrade() -> None:
    # Remove jobs table and indexes
    op.drop_index('jobs_next_run_at_idx', table_name='jobs')
    op.drop_index('jobs_idempotency_key_idx', table_name='jobs')
    op.drop_index('jobs_status_next_run_at_idx', table_name='jobs')
    op.drop_index('jobs_correlation_id_idx', table_name='jobs')
    op.drop_index('jobs_user_status_idx', table_name='jobs')
    op.drop_index('jobs_user_created_at_idx', table_name='jobs')
    op.drop_index('jobs_user_id_idx', table_name='jobs')
    op.drop_index('jobs_status_idx', table_name='jobs')
    op.drop_table('jobs')

    # Remove usage events
    op.drop_index('usage_events_stripe_event_id_idx', table_name='usage_events')
    op.drop_index('usage_events_user_time_idx', table_name='usage_events')
    op.drop_table('usage_events')

    # Remove usage counters
    op.drop_constraint('usage_counters_user_period_uniq', 'usage_counters', type_='unique')
    op.drop_index('usage_counters_user_idx', table_name='usage_counters')
    op.drop_table('usage_counters')

    # Remove subscriptions
    op.drop_index('subscriptions_status_idx', table_name='subscriptions')
    op.drop_index('subscriptions_user_id_idx', table_name='subscriptions')
    op.drop_table('subscriptions')

    # Remove users
    op.drop_index('users_email_idx', table_name='users')
    op.drop_table('users')

    # Note: citext extension intentionally left installed
