import pytest
from datetime import datetime, timezone, timedelta
from app.models.campaign import CampaignCreate, CampaignCreateInternal
from pydantic import ValidationError

def test_campaign_create_retry_until_future_strict():
    # Regular CampaignCreate requires retry_until to be strictly in the future
    past_date = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    with pytest.raises(ValidationError) as exc:
        CampaignCreate(
            restaurant_id="test_rest",
            name="Test",
            template_id="test_id",
            template_name="test_tpl",
            priority="MARKETING",
            contact_file_ref="test_ref",
            smart_retries=True,
            retry_until=past_date
        )
    assert "retry_until must be strictly in the future" in str(exc.value)

def test_campaign_create_internal_overrides_future_validation():
    # Internal model should bypass the future-date validation on retry_until
    past_date = datetime.now(timezone.utc) - timedelta(minutes=1)
    
    model = CampaignCreateInternal(
        restaurant_id="test_rest",
        name="Test",
        template_id="test_id",
        template_name="test_tpl",
        priority="MARKETING",
        contact_file_ref="test_ref",
        smart_retries=True,
        retry_until=past_date,
        parent_campaign_id="test",
        has_been_retried=False
    )
    
    # Should not raise, value is set correctly
    assert model.retry_until == past_date
