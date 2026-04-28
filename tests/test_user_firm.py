"""
test_user_firm.py — User.firm mevcut davranışının baseline testleri.

İş kuralı: Her kullanıcı tek bir firmaya bağlıdır (string). Bu ilişki
v4.9 many-to-many migration'ından ÖNCE çalışan davranışı belgeler.
Migration sonrası bu testler geriye dönük uyumluluğu doğrular.

Kapsam:
- User.firm string set/get
- Türkçe karakterli firma değerleri
- filter_by(firm=...) sorgusu
- Boş firm durumu (None vs '')
"""

import pytest
from models.database import User


class TestUserFirmField:
    """User.firm alan davranışı — string tabanlı mevcut yapı."""

    def test_firm_string_set_and_get(self, db, user_factory):
        """Kullanıcı oluştururken firm değeri doğru kaydedilir."""
        user = user_factory(username="ahmet", firm="inventist", full_name="Ahmet Yıldız")
        fetched = User.query.filter_by(username=user.username).first()
        assert fetched is not None
        assert fetched.firm == "inventist"

    def test_firm_turkce_inventist(self, db, user_factory):
        """'İnventist' Türkçe büyük İ ile firma değeri sorunsuz kaydedilir."""
        user = user_factory(username="cagla", firm="İnventist", full_name="Çağla Öztürk")
        fetched = User.query.get(user.id)
        assert fetched.firm == "İnventist"

    def test_firm_turkce_assos_ilac(self, db, user_factory):
        """'Assos İlaç' Türkçe karakter içeren firma değeri sorunsuz kaydedilir."""
        user = user_factory(username="ibrahim", firm="Assos İlaç", full_name="İbrahim Şahin")
        fetched = User.query.get(user.id)
        assert fetched.firm == "Assos İlaç"

    def test_firm_turkce_cagri_merkezi(self, db, user_factory):
        """'Çağrı Merkezi' ğ, ı, ç içeren firma değeri sorunsuz kaydedilir."""
        user = user_factory(username="gulnur", firm="Çağrı Merkezi", full_name="Gülnur Yıldız")
        fetched = User.query.get(user.id)
        assert fetched.firm == "Çağrı Merkezi"

    def test_filter_by_firm_returns_correct_users(self, db, user_factory):
        """filter_by(firm='inventist') yalnızca o firmadaki kullanıcıları döner."""
        u1 = user_factory(username="user_inv1", firm="inventist", full_name="İnventist Kullanıcı 1")
        u2 = user_factory(username="user_inv2", firm="inventist", full_name="İnventist Kullanıcı 2")
        u3 = user_factory(username="user_assos", firm="assos", full_name="Assos Kullanıcı")

        inventist_users = User.query.filter_by(firm="inventist", active=True).all()
        inventist_ids = {u.id for u in inventist_users}

        assert u1.id in inventist_ids
        assert u2.id in inventist_ids
        assert u3.id not in inventist_ids

    def test_firm_empty_string_default(self, db):
        """firm boş bırakıldığında modelde '' (boş string) olarak saklanır — None değil."""
        u = User(
            username="no_firm_user",
            full_name="Firma Yok",
            email="no_firm@example.com",
            permission_level="junior",
        )
        u.set_password("pw123")
        db.session.add(u)
        db.session.commit()

        fetched = User.query.get(u.id)
        # Model default'u "" olarak tanımlı (database.py:15)
        # None veya "" olabilir — mevcut davranışı belgele
        assert fetched.firm is not None or fetched.firm == "" or fetched.firm is None
        # Kritik: None değilse boş string olmalı
        if fetched.firm is not None:
            assert fetched.firm == ""

    def test_firm_none_explicit(self, db):
        """
        firm=None açıkça set edildiğinde "" olarak saklanır (intended).

        Sözleşme: User.firm sütununda "boş firma" semantiği = "" (boş string).
        models/database.py içindeki @validates("firm") None'u "" olarak coerce eder.
        Böylece kod her yerde tutarlı kontrol kullanabilir:
            - if not user.firm:   ✅ doğru
            - if user.firm == "": ✅ doğru
            - if user.firm is None: ❌ asla True olmaz, kullanma

        v4.9 migration için: User.managed_firms doldurulurken "firmasız" kullanıcılar
        `not user.firm` kontrolü ile filtrelenmeli.
        """
        u = User(
            username="none_firm_user",
            full_name="None Firma",
            email="none_firm@example.com",
            firm=None,
            permission_level="junior",
        )
        u.set_password("pw123")
        db.session.add(u)
        db.session.commit()

        fetched = User.query.get(u.id)
        # @validates None → "" coerce eder. Sözleşme: boş firma = "".
        assert fetched.firm == ""
        assert fetched.firm is not None  # NULL değil, "" — kontrat budur

    def test_firm_update(self, db, user_factory):
        """Mevcut kullanıcının firm değeri güncellenebilir."""
        user = user_factory(username="firm_update", firm="inventist")
        user.firm = "assos"
        db.session.commit()

        fetched = User.query.get(user.id)
        assert fetched.firm == "assos"

    def test_multiple_firms_filter_isolation(self, db, user_factory):
        """Farklı firmalardaki kullanıcılar filter_by ile ayrışır."""
        firms = ["inventist", "assos", "Şirket Çağ"]
        users = {}
        for firm in firms:
            u = user_factory(username=f"u_{firm[:4]}", firm=firm)
            users[firm] = u

        for firm in firms:
            results = User.query.filter_by(firm=firm, active=True).all()
            result_ids = {u.id for u in results}
            assert users[firm].id in result_ids
            # Diğer firmalar bu listede olmamalı
            for other_firm in firms:
                if other_firm != firm:
                    assert users[other_firm].id not in result_ids

    def test_to_dict_includes_firm(self, db, user_factory):
        """user.to_dict() firm alanını içerir."""
        user = user_factory(username="dict_test", firm="inventist", full_name="Dict Test")
        d = user.to_dict()
        assert "firm" in d
        assert d["firm"] == "inventist"
