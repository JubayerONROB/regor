"""Domain adapters.

A domain adapter is *data*, not code: suggested metrics, dataset checks, experiment
types, resource hints and extra report sections for a field. The core engine never
branches on the domain name -- it only reads the profile. Projects can override or add
a profile with ``domain.yaml`` at the project root, so an unlisted field needs no code.

Nothing here assumes epochs, accuracy, loss curves, neural networks or GPUs; those
appear only in the machine-learning profiles, as suggestions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .util import read_yaml


@dataclass
class MetricSuggestion:
    name: str
    direction: str                  # higher | lower | none
    unit: str = ""
    definition: str = ""


@dataclass
class DomainProfile:
    name: str
    description: str
    experiment_types: list[str] = field(default_factory=list)
    suggested_metrics: list[MetricSuggestion] = field(default_factory=list)
    dataset_checks: list[str] = field(default_factory=list)
    metadata_requirements: list[str] = field(default_factory=list)
    resource_hints: dict[str, Any] = field(default_factory=dict)
    report_sections: list[str] = field(default_factory=list)
    statistics_notes: str = ""
    src_dirs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DomainProfile":
        d = dict(d)
        d["suggested_metrics"] = [MetricSuggestion(**m) for m in d.get("suggested_metrics", [])]
        try:
            return cls(**d)
        except TypeError as exc:
            raise ConfigError(f"invalid domain profile: {exc}") from exc


M = MetricSuggestion
COMMON_TYPES = ["baseline", "proposed", "ablation", "sensitivity", "robustness",
                "replication"]
GENERIC_CHECKS = ["files_exist", "fingerprint", "missing_values", "duplicates",
                  "outliers", "column_ranges"]
ML_CHECKS = GENERIC_CHECKS + ["class_distribution", "split_integrity", "leakage",
                              "label_validity"]
MEASUREMENT_CHECKS = GENERIC_CHECKS + ["units", "instrument_metadata",
                                       "missing_observations"]

_BUILTIN: dict[str, DomainProfile] = {}


def _reg(p: DomainProfile) -> None:
    _BUILTIN[p.name] = p


_reg(DomainProfile(
    name="generic",
    description="No domain assumptions. Define metrics and checks per experiment.",
    experiment_types=COMMON_TYPES + ["exploratory"],
    dataset_checks=GENERIC_CHECKS,
    src_dirs=["preprocessing", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="machine_learning",
    description="Supervised/unsupervised learning on tabular or generic data.",
    experiment_types=COMMON_TYPES + ["generalization", "efficiency"],
    suggested_metrics=[M("accuracy", "higher", "fraction"), M("macro_f1", "higher", "fraction"),
                       M("auroc", "higher", "fraction"), M("log_loss", "lower", "nats"),
                       M("train_time", "lower", "s")],
    dataset_checks=ML_CHECKS,
    resource_hints={"device": "any"},
    report_sections=["Learning curves (if applicable)", "Error analysis"],
    statistics_notes="Report per-seed results; use paired tests when runs share splits.",
    src_dirs=["preprocessing", "models", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="computer_vision",
    description="Image/video recognition, detection, segmentation.",
    experiment_types=COMMON_TYPES + ["generalization", "efficiency"],
    suggested_metrics=[M("top1_accuracy", "higher", "fraction"), M("mAP", "higher", "fraction"),
                       M("mIoU", "higher", "fraction"), M("latency_ms", "lower", "ms")],
    dataset_checks=ML_CHECKS + ["image_integrity"],
    resource_hints={"device": "gpu"},
    report_sections=["Qualitative examples", "Failure cases"],
    src_dirs=["preprocessing", "models", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="nlp",
    description="Natural-language processing tasks.",
    experiment_types=COMMON_TYPES + ["generalization", "efficiency"],
    suggested_metrics=[M("macro_f1", "higher", "fraction"), M("exact_match", "higher", "fraction"),
                       M("bleu", "higher", "points"), M("perplexity", "lower", "")],
    dataset_checks=ML_CHECKS + ["text_encoding", "near_duplicates"],
    report_sections=["Qualitative examples", "Error taxonomy"],
    src_dirs=["preprocessing", "models", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="robotics",
    description="Robotics and autonomous systems (simulation or hardware trials).",
    experiment_types=COMMON_TYPES + ["simulation", "measurement", "generalization"],
    suggested_metrics=[M("success_rate", "higher", "fraction"),
                       M("tracking_error", "lower", "m"), M("time_to_goal", "lower", "s"),
                       M("collisions", "lower", "count")],
    dataset_checks=MEASUREMENT_CHECKS,
    metadata_requirements=["platform", "environment", "sensor_config"],
    report_sections=["Trial conditions", "Safety incidents"],
    src_dirs=["methods", "simulation", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="embedded_systems",
    description="Firmware, microcontrollers, hardware/software co-design.",
    experiment_types=COMMON_TYPES + ["measurement", "efficiency"],
    suggested_metrics=[M("latency_us", "lower", "us"), M("energy_mJ", "lower", "mJ"),
                       M("memory_kB", "lower", "kB"), M("throughput", "higher", "ops/s")],
    dataset_checks=MEASUREMENT_CHECKS,
    metadata_requirements=["board", "clock_mhz", "toolchain", "measurement_instrument"],
    report_sections=["Hardware setup", "Measurement procedure"],
    src_dirs=["firmware", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="electrical_engineering",
    description="Circuits, devices, electrical measurements.",
    experiment_types=COMMON_TYPES + ["measurement", "simulation"],
    suggested_metrics=[M("efficiency", "higher", "%"), M("thd", "lower", "%"),
                       M("rmse", "lower", "V"), M("power_loss", "lower", "W")],
    dataset_checks=MEASUREMENT_CHECKS,
    metadata_requirements=["instrument", "calibration_date", "sampling_rate_hz"],
    report_sections=["Measurement setup", "Instrument uncertainty"],
    src_dirs=["simulation", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="power_systems",
    description="Grid operation, load flow, stability, forecasting, protection.",
    experiment_types=COMMON_TYPES + ["simulation", "measurement", "generalization"],
    suggested_metrics=[M("mape", "lower", "%"), M("rmse", "lower", "MW"),
                       M("voltage_deviation", "lower", "p.u."),
                       M("loss_reduction", "higher", "%")],
    dataset_checks=MEASUREMENT_CHECKS + ["timestamp_continuity"],
    metadata_requirements=["test_system", "base_mva", "time_resolution"],
    report_sections=["Test system description", "Operating scenarios"],
    src_dirs=["simulation", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="signal_processing",
    description="Filtering, estimation, detection, spectral analysis.",
    experiment_types=COMMON_TYPES + ["simulation", "measurement"],
    suggested_metrics=[M("snr_db", "higher", "dB"), M("rmse", "lower", ""),
                       M("detection_probability", "higher", "fraction"),
                       M("false_alarm_rate", "lower", "fraction")],
    dataset_checks=MEASUREMENT_CHECKS + ["sampling_consistency"],
    metadata_requirements=["sampling_rate_hz"],
    report_sections=["Signal model", "Noise conditions"],
    src_dirs=["preprocessing", "methods", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="control_systems",
    description="Controller design, identification, stability and performance.",
    experiment_types=COMMON_TYPES + ["simulation", "measurement"],
    suggested_metrics=[M("settling_time", "lower", "s"), M("overshoot", "lower", "%"),
                       M("steady_state_error", "lower", ""), M("iae", "lower", "")],
    dataset_checks=MEASUREMENT_CHECKS,
    metadata_requirements=["plant_model", "sampling_time"],
    report_sections=["Plant model", "Disturbance scenarios"],
    src_dirs=["models", "controllers", "simulation", "analysis"],
))
_reg(DomainProfile(
    name="materials_science",
    description="Synthesis, characterisation and property measurement.",
    experiment_types=COMMON_TYPES + ["measurement", "simulation"],
    suggested_metrics=[M("tensile_strength", "higher", "MPa"),
                       M("conductivity", "higher", "S/m"), M("band_gap", "none", "eV")],
    dataset_checks=MEASUREMENT_CHECKS,
    metadata_requirements=["instrument", "sample_preparation", "temperature"],
    report_sections=["Sample preparation", "Characterisation methods"],
    src_dirs=["processing", "analysis"],
))
_reg(DomainProfile(
    name="biomedical_engineering",
    description="Biosignals, medical imaging, devices. Ethics metadata expected.",
    experiment_types=COMMON_TYPES + ["measurement", "generalization"],
    suggested_metrics=[M("sensitivity", "higher", "fraction"), M("specificity", "higher", "fraction"),
                       M("auroc", "higher", "fraction"), M("mae", "lower", "")],
    dataset_checks=ML_CHECKS + ["units", "subject_leakage"],
    metadata_requirements=["ethics_approval", "subject_count", "acquisition_device"],
    report_sections=["Ethics and consent", "Subject-level analysis"],
    statistics_notes="Split and resample by subject, never by sample, to avoid leakage.",
    src_dirs=["preprocessing", "models", "evaluation", "analysis"],
))
_reg(DomainProfile(
    name="physics",
    description="Experimental or computational physics.",
    experiment_types=COMMON_TYPES + ["measurement", "simulation"],
    suggested_metrics=[M("chi2_per_dof", "none", ""), M("relative_error", "lower", "")],
    dataset_checks=MEASUREMENT_CHECKS,
    metadata_requirements=["apparatus", "calibration"],
    report_sections=["Systematic uncertainties"],
    src_dirs=["simulation", "analysis"],
))
_reg(DomainProfile(
    name="computational_science",
    description="Numerical simulation and scientific computing.",
    experiment_types=COMMON_TYPES + ["simulation", "efficiency"],
    suggested_metrics=[M("relative_error", "lower", ""), M("wall_time", "lower", "s"),
                       M("convergence_order", "higher", "")],
    dataset_checks=GENERIC_CHECKS,
    report_sections=["Numerical settings", "Convergence study"],
    src_dirs=["solvers", "simulation", "analysis"],
))

ALIASES = {"ml": "machine_learning", "ai": "machine_learning", "cv": "computer_vision",
           "eee": "electrical_engineering", "electrical": "electrical_engineering",
           "biomedical": "biomedical_engineering", "embedded": "embedded_systems"}


def available() -> list[str]:
    return sorted(_BUILTIN)


def get_profile(name: str, project_root: Path | None = None) -> DomainProfile:
    """Built-in profile, overridden/extended by <project>/domain.yaml when present."""
    key = ALIASES.get(name, name)
    custom = read_yaml(project_root / "domain.yaml") if project_root else None
    if custom:
        base = _BUILTIN.get(key, _BUILTIN["generic"]).to_dict()
        base.update(custom)
        base.setdefault("name", key)
        return DomainProfile.from_dict(base)
    if key not in _BUILTIN:
        raise ConfigError(
            f"unknown domain {name!r}. Built-in: {', '.join(available())}. "
            "Use --domain generic, or add a domain.yaml to the project.")
    return _BUILTIN[key]
