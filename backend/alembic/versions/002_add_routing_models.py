"""Add routing models - depots, orders, zone_depot_assignments

Revision ID: 002_add_routing_models
Revises: 001_initial_tables
Create Date: 2025-01-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_routing_models'
down_revision: Union[str, None] = '001_initial_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create order_status_enum type
    order_status_enum = postgresql.ENUM(
        'pending', 'geocoded', 'assigned', 'in_transit', 'delivered', 'failed', 'cancelled',
        name='order_status_enum',
        create_type=False
    )
    order_status_enum.create(op.get_bind(), checkfirst=True)
    
    # Create depots table
    op.create_table('depots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('address', sa.String(length=500), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('h3_index', sa.String(length=20), nullable=True, comment='H3 cell for depot location'),
        sa.Column('available_drivers', sa.Integer(), nullable=False, comment='Available drivers for route optimization', server_default='5'),
        sa.Column('contact_info', sa.String(length=500), nullable=True, comment='Contact phone/email'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('available_drivers >= 0', name='check_available_drivers_positive'),
        sa.CheckConstraint('latitude >= -90 AND latitude <= 90', name='check_depot_latitude_range'),
        sa.CheckConstraint('longitude >= -180 AND longitude <= 180', name='check_depot_longitude_range'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index('ix_depots_name', 'depots', ['name'], unique=True)
    op.create_index('idx_depots_h3_index', 'depots', ['h3_index'], unique=False)
    op.create_index('idx_depots_location', 'depots', ['latitude', 'longitude'], unique=False)
    op.create_index('idx_depots_is_active', 'depots', ['is_active'], unique=False, postgresql_where=sa.text('is_active = true'))
    
    # Create orders table
    op.create_table('orders',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('order_number', sa.String(length=100), nullable=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False),
        sa.Column('customer_contact', sa.String(length=255), nullable=True, comment='Phone or email'),
        sa.Column('delivery_address', sa.TEXT(), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('h3_index', sa.String(length=20), nullable=False, comment='H3 cell for order location'),
        sa.Column('zone_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('depot_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('order_date', sa.Date(), nullable=False),
        sa.Column('scheduled_delivery_date', sa.Date(), nullable=True),
        sa.Column('status', postgresql.ENUM(
            'pending', 'geocoded', 'assigned', 'in_transit', 'delivered', 'failed', 'cancelled',
            name='order_status_enum',
            create_type=False
        ), nullable=False, server_default='pending'),
        sa.Column('weight_kg', sa.Float(), nullable=True),
        sa.Column('volume_m3', sa.Float(), nullable=True),
        sa.Column('special_instructions', sa.TEXT(), nullable=True),
        sa.Column('cluster_id', sa.Integer(), nullable=True, comment='HDBSCAN cluster assignment'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('latitude >= -90 AND latitude <= 90', name='check_order_latitude_range'),
        sa.CheckConstraint('longitude >= -180 AND longitude <= 180', name='check_order_longitude_range'),
        sa.CheckConstraint('weight_kg >= 0', name='check_weight_positive'),
        sa.CheckConstraint('volume_m3 >= 0', name='check_volume_positive'),
        sa.ForeignKeyConstraint(['zone_id'], ['service_zones.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['depot_id'], ['depots.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_number')
    )
    op.create_index('ix_orders_order_number', 'orders', ['order_number'], unique=True)
    op.create_index('idx_orders_h3_index', 'orders', ['h3_index'], unique=False)
    op.create_index('idx_orders_zone_id', 'orders', ['zone_id'], unique=False)
    op.create_index('idx_orders_depot_id', 'orders', ['depot_id'], unique=False)
    op.create_index('ix_orders_order_date', 'orders', ['order_date'], unique=False)
    op.create_index('ix_orders_scheduled_delivery_date', 'orders', ['scheduled_delivery_date'], unique=False)
    op.create_index('idx_orders_location', 'orders', ['latitude', 'longitude'], unique=False)
    op.create_index('idx_orders_depot_date', 'orders', ['depot_id', 'scheduled_delivery_date'], unique=False)
    op.create_index('idx_orders_status', 'orders', ['status'], unique=False)
    
    # Create zone_depot_assignments table
    op.create_table('zone_depot_assignments',
        sa.Column('zone_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('depot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('priority', sa.Integer(), nullable=False, comment='Priority order if multiple depots', server_default='1'),
        sa.ForeignKeyConstraint(['zone_id'], ['service_zones.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['depot_id'], ['depots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('zone_id', 'depot_id')
    )
    op.create_index('idx_zone_depot_zone_id', 'zone_depot_assignments', ['zone_id'], unique=False)
    op.create_index('idx_zone_depot_depot_id', 'zone_depot_assignments', ['depot_id'], unique=False)


def downgrade() -> None:
    # Drop tables
    op.drop_table('zone_depot_assignments')
    op.drop_table('orders')
    op.drop_table('depots')
    
    # Drop enum type
    postgresql.ENUM(name='order_status_enum').drop(op.get_bind(), checkfirst=True)
