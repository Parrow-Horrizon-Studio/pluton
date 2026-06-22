from __future__ import annotations

from pluton.viewport.face_batches import FaceBatch, plan_face_batches


def test_empty_returns_no_batches():
    order, batches = plan_face_batches([])
    assert order.tolist() == []
    assert batches == []


def test_single_material_one_batch_identity_order():
    order, batches = plan_face_batches([0, 0, 0])      # 3 triangles, all Default
    assert order.tolist() == list(range(9))            # identity over 9 vertices
    assert batches == [FaceBatch(material_id=0, first=0, count=9)]


def test_default_only_collapses_to_one_default_batch():
    order, batches = plan_face_batches([0, 0, 0, 0])
    assert batches == [FaceBatch(material_id=0, first=0, count=12)]
    assert order.tolist() == list(range(12))           # identity → byte-identical path


def test_interleaved_materials_grouped_and_contiguous():
    # triangles: mat 2, mat 0, mat 2, mat 0  -> grouped 0,0 then 2,2
    order, batches = plan_face_batches([2, 0, 2, 0])
    assert batches == [
        FaceBatch(material_id=0, first=0, count=6),
        FaceBatch(material_id=2, first=6, count=6),
    ]
    # mat-0 tris are originals 1 and 3 (verts 3,4,5 and 9,10,11), then mat-2.
    assert order.tolist() == [3, 4, 5, 9, 10, 11, 0, 1, 2, 6, 7, 8]


def test_vertex_order_is_a_valid_permutation():
    order, _ = plan_face_batches([5, 1, 5, 1, 9])
    assert sorted(order.tolist()) == list(range(15))
