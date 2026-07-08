from src.core.types import Bar
from src.displacement.d1_body import D1_DEFAULT_PARAMS, D1BodyRatio
from src.fvg.engine import FVGEngine
from src.store.state_store import StateStore
from src.structure.engine import StructureEngine


def run_pipeline(bars: list[Bar]) -> StateStore:
    """Feed ``bars`` through a fresh StructureEngine+FVGEngine (one TF, bias-source), in order."""
    store = StateStore()
    if not bars:
        return store
    tf = bars[0].tf
    structure = StructureEngine(tf, is_bias_source=True)
    fvg = FVGEngine(tf, displacement_model=D1BodyRatio(), displacement_params=D1_DEFAULT_PARAMS)
    for bar in bars:
        structure.step(bar, store)
        fvg.step_bar_close(bar, store)
    return store
