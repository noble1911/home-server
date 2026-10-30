"""Profile update validation (no database).

Run with: pytest butler/api/test_profile_update.py -v
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from .models import UpdateProfileRequest


@pytest.mark.parametrize("email", ["noble1911@gmail.com", " Ron@Example.co.uk ", ""])
def test_accepts_emails_and_blank(email):
    assert UpdateProfileRequest(email=email).email == email


@pytest.mark.parametrize("email", ["ron", "ron@", "ron@localhost", "a b@c.com", "x@y@z.com"])
def test_rejects_malformed_emails(email):
    with pytest.raises(ValidationError):
        UpdateProfileRequest(email=email)
