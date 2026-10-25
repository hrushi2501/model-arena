# Training pipeline

DVC owns dataset references and reproducible prepare/train/evaluate stages. MLflow records runs, metrics, artifacts, and registered model versions. The MLflow server runs from `infra/mlflow/`; serving deployments should resolve an alias to a concrete version and record that version.

Add the first stages to `dvc.yaml` when the dataset and evaluation metrics have been selected. Keep source data and trained artifacts out of Git; configure a DVC remote and MLflow artifact store for the chosen environment.

## Dataset and signature contract (proposal)

> **Status: PROPOSED** — pending review by Lane B (Hrushi) and Lanes C/D.

### Dataset
- scikit-learn Wine recognition dataset (`sklearn.datasets.load_wine`)
- 178 rows
- 3 target classes labeled `0`, `1`, `2` (`class_0`, `class_1`, `class_2`)

### Features (Signature version 1)
13 float features in fixed order using snake_case names derived from `load_wine().feature_names` (replacing `/` with `_`):
1. `alcohol` (float)
2. `malic_acid` (float)
3. `ash` (float)
4. `alcalinity_of_ash` (float)
5. `magnesium` (float)
6. `total_phenols` (float)
7. `flavanoids` (float)
8. `nonflavanoid_phenols` (float)
9. `proanthocyanins` (float)
10. `color_intensity` (float)
11. `hue` (float)
12. `od280_od315_of_diluted_wines` (float)
13. `proline` (float)

### Validation rules
- All 13 features are required.
- All values must be numeric and finite (no `NaN`, `+Inf`, or `-Inf`).
- No extra fields permitted in prediction request payloads.
- Target labels must never be included in prediction requests.
- Signature version: `1`.

### Split strategy
- Stratified train/validation/test split: 60% train, 20% validation, 20% test (60/20/20).
- Random seed: `42`.
- Test data is used only for the final offline evaluation and comparison, never for training or hyperparameter tuning.

### Metrics
- Offline evaluation metrics: `macro-F1` and `accuracy`.
- Evaluated on the identical held-out test split for both champion (`RandomForestClassifier`) and candidate (`GradientBoostingClassifier`) models.
