from motor.motor_asyncio import AsyncIOMotorDatabase
from app.database import get_db, get_fielia_db
from app.services.phone_normalizer import phone_normalizer

class MemberMatchService:
    @staticmethod
    async def get_member_db_context(rid: str):
        """
        Returns the appropriate DB and collection for a given restaurant_id.
        Handles Local vs Fielia External logic.
        """
        local_db = get_db()
        
        if rid == "r2":
            f_db = get_fielia_db()
            if f_db is not None:
                # Fielia members are in 'test.cards'
                return f_db.client.get_database("test"), "cards", {}
        
        return local_db, "members", {"restaurant_id": rid}

    @staticmethod
    async def match_member(rid: str, phone: str):
        """
        Finds a member by phone across the appropriate database.
        """
        normalized = phone_normalizer.normalize(phone)
        if not normalized:
            return None
            
        m_db, m_coll, m_filter = await MemberMatchService.get_member_db_context(rid)
        
        member = await m_db[m_coll].find_one({
            **m_filter,
            "normalized_phone": normalized
        })
        
        return member

member_match_service = MemberMatchService()
