# Architecture Diagram

```mermaid
flowchart TD
    A[20 Symbol Universe] --> B[Multi-Timeframe Klines]
    B --> C[Canonical State Builder]
    C --> D[Shared Feature Engine]
    D --> E[Unsupervised Context Layer]
    D --> F[V7 Simulation Label Adapter]
    E --> G[Mode-Specific Datasets]
    F --> G
    G --> H1[SWING XGBoost Bundle]
    G --> H2[SCALP XGBoost Bundle]
    G --> H3[AGGRESSIVE XGBoost Bundle]
    H1 --> I[Calibration & Reliability]
    H2 --> I
    H3 --> I
    I --> J[Alpha Score Builder]
    J --> K[V7 Decision Engine]
    K --> L[Policy / Portfolio / Risk]
    L --> M[Execution or NO_TRADE]
```


## Review-hardened anomaly lineage

```mermaid
flowchart TD
  Fold[Walk-forward fold] --> TrainWindow[Fold train window only]
  TrainWindow --> FitAnomaly[Fit anomaly/regime artifact]
  FitAnomaly --> Artifact[Fold-scoped anomaly artifact]
  Artifact --> TransformVal[Transform validation/holdout/live rows]
  TransformVal --> Lineage[Feature rows with anomaly fit lineage]
  Lineage --> BoundaryCheck[Dataset boundary check]
  BoundaryCheck --> Dataset[Mode-specific dataset]
```
