"""Initial migration - create tables

Revision ID: 001_initial_tables
Revises: 
Create Date: 2025-11-10 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import geoalchemy2
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_tables'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create h3_compacts table (SQLAlchemy will auto-create the enum types)
    op.create_table('h3_compacts',
        sa.Column('owner_kind', sa.Enum('SERVICE_AREA', 'SERVICE_ZONE', name='owner_kind_enum'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('resolution', sa.SmallInteger(), nullable=False),
        sa.Column('method', sa.Enum('CENTROID', 'COVERAGE', name='h3_method_enum'), nullable=False),
        sa.Column('cells_compact', sa.ARRAY(sa.String(length=20)), nullable=False, comment='Array of compacted H3 cell IDs'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('resolution >= 0 AND resolution <= 15', name='check_resolution_range_compacts'),
        sa.PrimaryKeyConstraint('owner_kind', 'owner_id', 'resolution', 'method')
    )
    
    # Create h3_covers table
    op.create_table('h3_covers',
        sa.Column('owner_kind', sa.Enum('SERVICE_AREA', 'SERVICE_ZONE', name='owner_kind_enum'), nullable=False),
        sa.Column('owner_id', sa.UUID(), nullable=False),
        sa.Column('resolution', sa.SmallInteger(), nullable=False),
        sa.Column('method', sa.Enum('CENTROID', 'COVERAGE', name='h3_method_enum'), nullable=False),
        sa.Column('cell', sa.String(length=20), nullable=False, comment='H3 cell ID'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('resolution >= 0 AND resolution <= 15', name='check_resolution_range_covers'),
        sa.PrimaryKeyConstraint('owner_kind', 'owner_id', 'resolution', 'method', 'cell')
    )
    op.create_index('idx_h3_covers_cell', 'h3_covers', ['cell'], unique=False)
    op.create_index('idx_h3_covers_owner', 'h3_covers', ['owner_kind', 'owner_id', 'resolution'], unique=False)
    
    # Create service_areas table
    op.create_table('service_areas',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.TEXT(), nullable=True),
        sa.Column('boundary', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry', spatial_index=True, nullable=False), nullable=False),
        sa.Column('label_cell', sa.String(length=20), nullable=True, comment='H3 cell ID for representative hex'),
        sa.Column('default_res', sa.SmallInteger(), nullable=False, comment='Default H3 resolution'),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('default_res >= 0 AND default_res <= 15', name='check_default_res_range_areas'),
        sa.PrimaryKeyConstraint('id'),
        sa.Index('ix_service_areas_name', 'name', unique=True),
        sa.Index('idx_service_areas_is_active', 'is_active', postgresql_where=sa.text('is_active = true'))
    )
    # Note: spatial index for boundary is auto-created by GeoAlchemy2
    
    # Create service_zones table
    op.create_table('service_zones',
        sa.Column('service_area_id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=True, comment='FSA or internal code'),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('boundary', geoalchemy2.types.Geometry(geometry_type='MULTIPOLYGON', srid=4326, from_text='ST_GeomFromEWKT', name='geometry', spatial_index=True, nullable=False), nullable=False),
        sa.Column('label_cell', sa.String(length=20), nullable=True, comment='H3 cell ID for representative hex'),
        sa.Column('default_res', sa.SmallInteger(), nullable=False, comment='Default H3 resolution'),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('default_res >= 0 AND default_res <= 15', name='check_default_res_range_zones'),
        sa.ForeignKeyConstraint(['service_area_id'], ['service_areas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service_area_id', 'name', name='uq_service_zone_area_name'),
        sa.Index('idx_service_zones_service_area_id', 'service_area_id'),
        sa.Index('idx_service_zones_is_active', 'is_active', postgresql_where=sa.text('is_active = true'))
    )
    # Note: spatial index for boundary is auto-created by GeoAlchemy2


def downgrade() -> None:
    """
    Complete cleanup - drops all tables, indexes, and data.
    Use this to completely reset the database schema.
    """
    # Drop indexes first (with IF EXISTS to handle partial migrations)
    op.execute('DROP INDEX IF EXISTS ix_service_zones_service_area_id CASCADE')
    op.execute('DROP INDEX IF EXISTS ix_service_zones_is_active CASCADE')
    op.execute('DROP INDEX IF EXISTS idx_service_zones_service_area_id CASCADE')
    op.execute('DROP INDEX IF EXISTS idx_service_zones_is_active CASCADE')
    op.execute('DROP INDEX IF EXISTS idx_service_zones_boundary CASCADE')
    
    op.execute('DROP INDEX IF EXISTS ix_service_areas_name CASCADE')
    op.execute('DROP INDEX IF EXISTS ix_service_areas_is_active CASCADE')
    op.execute('DROP INDEX IF EXISTS idx_service_areas_is_active CASCADE')
    op.execute('DROP INDEX IF EXISTS idx_service_areas_boundary CASCADE')
    
    op.execute('DROP INDEX IF EXISTS idx_h3_covers_owner CASCADE')
    op.execute('DROP INDEX IF EXISTS idx_h3_covers_cell CASCADE')
    
    # Drop tables (with CASCADE to handle foreign keys)
    op.execute('DROP TABLE IF EXISTS service_zones CASCADE')
    op.execute('DROP TABLE IF EXISTS service_areas CASCADE')
    op.execute('DROP TABLE IF EXISTS h3_covers CASCADE')
    op.execute('DROP TABLE IF EXISTS h3_compacts CASCADE')
    
    # Drop enums (CASCADE will handle any dependencies)
    op.execute('DROP TYPE IF EXISTS h3_method_enum CASCADE')
    op.execute('DROP TYPE IF EXISTS owner_kind_enum CASCADE')
    
    print('✓ All schema and data cleaned successfully')

