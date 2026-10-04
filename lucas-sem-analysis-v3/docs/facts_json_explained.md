# What is in `facts.json`

Every image the pipeline processes produces one `facts.json`. It is the **only** thing the LLM reads: plain text
and numbers, no images. The answer comes first; the evidence behind it comes after.

## The fields, in order

| Field | What it tells you |
|---|---|
| `summary_sentences` | Plain-English sentences filled in from the numbers below. The LLM narrates these |
| `field_guide` | Tells the reader that `decision` is the final answer |
| `decision` | **The answer**: a batch, "Batch_1 or Batch_2", "unsure (leaning X)", a known location, or refused. Also the confidence tier, reasons, probabilities and track record |
| `phases` | Composition: pore / carbon / SiOx %, plus the experimental graphite-vs-binder split |
| `known_location_check` | Is this a training image, or a spot we already know? |
| `material_range_rule` | Does the composition, with GET4 error bars, fit only one batch's range? |
| `fingerprint_model` | Imaging-fingerprint model: probabilities, per detector, and the measurements that pushed hardest |
| `texture_model` | Tile texture model: shown for information, does not vote |
| `material_model` | Segmentation + DINOv2 model, including `map_text` (the maps described in words) |
| `qc`, `acquisition`, `novelty` | Quality checks and "unlike anything seen before" flags |
| `decision_v2`, `forced_mode` | The previous rule's answer, and the always-answer variant |
| `timings_s` | Seconds per step |

## Real example (trimmed)

Demo image `71vgq3fw` (true batch: Batch_3), run as a new image. `"..."` marks where the file was shortened.
The full file is `wechat-send-v3/output/facts.json`.

```json
{
  "summary_sentences": [
    "Answer: Batch_3 (High confidence); the imaging side (fingerprint) picked Batch_3 and the material side (segmentation + DINOv2) Batch_3.",
    "Reasons: both sides agree and the average calibrated probability is above the 90%-accuracy level; no warning flags.",
    "Track record of High-confidence answers: 10/12 right (83%) in nested leave-one-location-out tests.",
    "Composition: pore 16.7 %, carbon (graphite + binder) 76.8 %, SiOx 6.5 % (binder alone 13.2 %, experimental).",
    "Strongest imaging-fingerprint cue (BSE image): overall graininess is lower than typical (robust z -3.0).",
    "..."
  ],
  "field_guide": "Read `decision` first: it is the final answer ...",
  "sample_id": "img_71vgq3fw",
  "decision": {
    "answer": "Batch_3",
    "answer_type": "specific",
    "confidence": "High",
    "leaning": "Batch_3",
    "imaging_side_pick": "Batch_3",
    "material_side_pick": "Batch_3",
    "sides_agree": true,
    "prediction_set": [
      "Batch_3"
    ],
    "average_calibrated_probabilities": {
      "Batch_1": 0.043,
      "Batch_2": 0.098,
      "Batch_3": 0.859
    },
    "high_tier_threshold": 0.465,
    "reasons": [
      "both sides agree and the average calibrated probability is above the 90%-accuracy level; no warning flags"
    ],
    "track_record": {
      "LOO": {
        "this_confidence_tier": {
          "correct": "10/12",
          "accuracy": 0.833,
          "ci95": [
            0.552,
            0.953
          ]
        },
        "...": "..."
      }
    },
    "basis": "all models retrained, calibrated and thresholded without this location (hold-out demo)"
  },
  "phases": {
    "four_class_pct": {
      "pore": 16.7,
      "graphite": 63.61,
      "SiOx": 6.45,
      "CBD": 13.24
    },
    "three_class_pct": {
      "pore": 16.7,
      "carbon (graphite + binder)": 76.85,
      "SiOx": 6.45
    },
    "reliability": "pore / carbon / SiOx are reliable (87 % agreement with an independent annotator); the graphite-vs-binder split is experimental (binder precision ~50 %)"
  },
  "known_location_check": {
    "status": "new",
    "matches": [
      {
        "view": "BSE",
        "best_score_sd": 10.8,
        "location": "mgxahqnk",
        "batch": "Batch_3",
        "reference_detector": "BSE",
        "next_best_other_score_sd": 9.6
      },
      "..."
    ],
    "note": "no reference image matches at >= 15 SD with a 2x margin; treated as a new location"
  },
  "material_range_rule": {
    "answer": null,
    "votes": [],
    "phases": [
      {
        "phase": "pore",
        "pct": 16.68,
        "ci95": [
          15.09,
          18.27
        ],
        "fits_ranges_of": [
          "Batch_1",
          "Batch_2",
          "Batch_3"
        ],
        "ranges": {
          "Batch_1": [
            11.12,
            17.39
          ],
          "Batch_2": [
            13.76,
            23.57
          ],
          "Batch_3": [
            15.14,
            23.04
          ]
        }
      },
      "..."
    ]
  },
  "fingerprint_model": {
    "probabilities": {
      "Batch_1": 0.0,
      "Batch_2": 0.0,
      "Batch_3": 1.0
    },
    "per_view": {
      "BSE": {
        "Batch_1": 0.0,
        "Batch_2": 0.0,
        "Batch_3": 1.0
      },
      "...": "..."
    },
    "views_agree": true,
    "top_measurements": [
      {
        "view": "BSE",
        "measurement": "bse_noise_sd",
        "meaning": "overall graininess",
        "robust_z": -3.0,
        "direction": "low",
        "push_toward_winner": 4.598
      },
      {
        "view": "BSE",
        "measurement": "bse_row_banding_sd",
        "meaning": "line-to-line brightness jitter",
        "robust_z": -3.0,
        "direction": "low",
        "push_toward_winner": 3.366
      },
      "..."
    ]
  },
  "texture_model": {
    "used_in_decision": false,
    "why_not_used": "in nested leave-one-out it lowered accuracy when answering from 85 % to 80 %, so it is shown for information only",
    "calibrated_probabilities": {
      "Batch_1": 0.001,
      "Batch_2": 0.017,
      "Batch_3": 0.982
    },
    "top_features": [
      {
        "feature": "glcm_homogeneity_d1_y",
        "meaning": "smoothness between neighbouring pixels",
        "mean_z": 1.77,
        "push_toward_winner": 0.802
      },
      "..."
    ]
  },
  "material_model": {
    "probabilities": {
      "fused_F": {
        "Batch_1": 0.13,
        "Batch_2": 0.237,
        "Batch_3": 0.634
      },
      "...": "..."
    },
    "features_S": {
      "siox_frac": {
        "value": 6.4496,
        "robust_z": 0.78,
        "push_toward_winner_vs_runner_up": 0.169
      },
      "...": "..."
    },
    "map_text": {
      "sentences": [
        "DINOv2 evidence map: 58 % of the evidence for Batch_3 (over Batch_2) lies on graphite, which covers 64 % of the image.",
        "DINOv2 evidence for the prediction is concentrated on SiOx (2.2x its share of the image).",
        "DINOv2 evidence map: 62 % of the evidence against Batch_3 (for Batch_2) lies on graphite.",
        "..."
      ],
      "evidence_by_phase": {
        "positive": {
          "SiOx": {
            "share_pct": 13.9,
            "enrichment_vs_area": 2.16
          },
          "...": "..."
        },
        "...": "..."
      },
      "spatial": {
        "grid_3x3_pct": {
          "middle-centre": {
            "pore": 16.3,
            "graphite": 57.3,
            "SiOx": 11.7,
            "CBD": 14.7
          },
          "...": "..."
        },
        "notable_regions": [
          {
            "region": "middle-centre",
            "phase": "SiOx",
            "region_pct": 11.7,
            "image_pct": 6.4,
            "direction": "enriched"
          },
          "..."
        ]
      },
      "objects": {
        "largest_pores": [
          {
            "area_um2": 69.67,
            "length_um": 31.95,
            "width_um": 9.06,
            "orientation": "diagonal",
            "location": "middle-left",
            "centre_um": [
              37.4,
              20.6
            ]
          },
          "..."
        ],
        "largest_SiOx_particles": [
          {
            "area_um2": 39.58,
            "diameter_um": 7.1,
            "location": "middle-centre",
            "centre_um": [
              80.0,
              29.7
            ]
          },
          "..."
        ],
        "...": "..."
      },
      "...": "..."
    },
    "...": "..."
  },
  "qc": {
    "excluded_pct": 1.0,
    "cu_foil_detected": false,
    "manual_exclusion": false,
    "detectors_used": [
      "BSE",
      "Inlens"
    ]
  },
  "novelty": {
    "unusual_features_abs_robust_z_ge_3": [],
    "novel_acquisition": false
  },
  "decision_v2": {
    "answer": "Batch_3",
    "...": "..."
  },
  "forced_mode": {
    "answer": "Batch_3",
    "route": "fingerprint model: Batch_3"
  },
  "timings_s": {
    "total_s": 49.11,
    "...": "..."
  }
}
```

## How to read it in three steps
1. **`decision.answer` + `decision.confidence`:** what the system concludes and how sure it is.
2. **`decision.track_record`:** how often answers like this were right on locations the models never saw.
3. **Everything below `decision`:** the evidence. Composition, the imaging and material cues, and the maps in
   words. The individual models' own picks are inputs, not the answer.
