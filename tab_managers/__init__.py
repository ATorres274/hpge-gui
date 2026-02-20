from .histogram_tab import HistogramPreviewRenderer, HistogramTab
from .batch_tab import BatchProcessingTab
from .browser_tab import BrowserTab
from .tab_registry import registry as registry

__all__ = [
	"HistogramPreviewRenderer",
	"HistogramTab",
	"BatchProcessingTab",
	"BrowserTab",
	"registry",
]
