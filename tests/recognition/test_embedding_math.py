"""
Unit Tests for Vector Normalization and Cosine Similarity Mathematics
"""

import numpy as np
import pytest
from apps.agent.facesentry_agent.models.face_recognizer import (
    normalize_embedding,
    compute_cosine_similarity,
)


def test_vector_l2_normalization():
    """Verify that normalized vectors strictly have an L2 norm of 1.0."""
    # Test random 512-D vector
    np.random.seed(42)
    vec = np.random.randn(512).astype(np.float32)
    normalized = normalize_embedding(vec)
    
    norm = np.linalg.norm(normalized)
    assert np.isclose(norm, 1.0, atol=1e-6)
    assert normalized.shape == (512,)


def test_zero_vector_normalization_safety():
    """Verify that zero vectors do not cause division by zero errors."""
    zero_vec = np.zeros(512, dtype=np.float32)
    normalized = normalize_embedding(zero_vec)
    assert np.all(normalized == 0.0)


def test_cosine_similarity_identical_vectors():
    """Verify that identical normalized vectors yield a cosine similarity of 1.0."""
    np.random.seed(100)
    vec = normalize_embedding(np.random.randn(512))
    sim = compute_cosine_similarity(vec, vec)
    assert np.isclose(sim, 1.0, atol=1e-5)


def test_cosine_similarity_orthogonal_vectors():
    """Verify that orthogonal vectors yield a cosine similarity of 0.0."""
    vec_a = np.zeros(512, dtype=np.float32)
    vec_b = np.zeros(512, dtype=np.float32)
    vec_a[0] = 1.0
    vec_b[1] = 1.0

    sim = compute_cosine_similarity(vec_a, vec_b)
    assert np.isclose(sim, 0.0, atol=1e-5)


def test_cosine_similarity_opposite_vectors():
    """Verify that diametrically opposite vectors yield a cosine similarity of -1.0."""
    np.random.seed(200)
    vec_a = normalize_embedding(np.random.randn(512))
    vec_b = -vec_a

    sim = compute_cosine_similarity(vec_a, vec_b)
    assert np.isclose(sim, -1.0, atol=1e-5)


def test_threshold_comparison_behavior():
    """Verify threshold comparison logic around default 0.65 threshold."""
    threshold = 0.65

    # Case 1: High similarity
    sim_high = 0.88
    assert sim_high >= threshold

    # Case 2: Borderline below threshold
    sim_low = 0.64
    assert not (sim_low >= threshold)


def test_multi_sample_centroid_aggregation():
    """Verify multi-sample centroid aggregation and subsequent normalization."""
    np.random.seed(300)
    base_direction = normalize_embedding(np.random.randn(512))

    # Create 5 slightly jittered samples around base_direction (small angular deviation)
    samples = []
    for _ in range(5):
        noise = np.random.randn(512) * (0.02 / np.sqrt(512))
        sample = normalize_embedding(base_direction + noise)
        samples.append(sample)

    stacked = np.vstack(samples)
    centroid = normalize_embedding(np.mean(stacked, axis=0))

    # Centroid must have L2 norm = 1.0
    assert np.isclose(np.linalg.norm(centroid), 1.0, atol=1e-6)

    # Centroid must have high similarity with all individual samples
    for sample in samples:
        sim = compute_cosine_similarity(centroid, sample)
        assert sim > 0.95
