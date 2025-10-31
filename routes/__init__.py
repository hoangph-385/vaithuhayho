"""
Routes Package
"""

from .wms import bp as wms_bp
from .report import bp as report_bp

__all__ = ['wms_bp', 'report_bp']
