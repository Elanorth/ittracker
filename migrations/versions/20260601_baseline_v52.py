"""baseline v5.2 — mevcut schema state

Bu revision IT Tracker v5.2 prod ve staging DB'lerinin "şu anki" durumunu işaretler.

İçerik boş (upgrade/downgrade pass): mevcut DB'ler zaten bu noktada,
init_db() tarafından oluşturulmuş ve idempotent ALTER'larla v5.2 schema'sına
ulaşmış durumdalar.

Yeni geliştirici makinesi için: init_db() schema'yı kurar, sonra `flask db
stamp head` ile bu baseline'a stamp'lenir. Sonraki gerçek schema değişiklikleri
yeni revision'lar olarak gelir.

Revision ID: 20260601_baseline_v52
Revises: (none — baseline)
Create Date: 2026-06-01
"""

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


# revision identifiers, used by Alembic.
revision = "20260601_baseline_v52"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Baseline — mevcut DB'ler zaten bu noktada.
    # Yeni schema değişiklikleri sonraki revision'larda gelir.
    pass


def downgrade():
    # Baseline'ın altına inilmez (boş DB anlamına gelir).
    pass
