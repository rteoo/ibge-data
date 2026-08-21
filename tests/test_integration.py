from __future__ import annotations

import pytest


@pytest.mark.integration
def test_live_sidra_is_opt_in() -> None:
    pytest.skip("Live IBGE access is intentionally opt-in and not run offline")
