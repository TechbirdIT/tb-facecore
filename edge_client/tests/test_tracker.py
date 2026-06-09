# edge_client/tests/test_tracker.py
from edge_client.tracker import Tracker, iou


def test_iou_identical_is_one():
    assert iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0


def test_iou_disjoint_is_zero():
    assert iou([0, 0, 10, 10], [100, 100, 110, 110]) == 0.0


def test_iou_half_overlap():
    # two 10x10 boxes overlapping in a 5x10 strip: inter=50, union=150
    assert abs(iou([0, 0, 10, 10], [5, 0, 15, 10]) - (50 / 150)) < 1e-9


def test_new_detection_creates_track():
    t = Tracker()
    visible = t.update([[0, 0, 10, 10]])
    assert len(visible) == 1
    track, idx = visible[0]
    assert idx == 0 and t.active == 1 and track.age == 1


def test_same_face_keeps_track_id():
    t = Tracker()
    id1 = t.update([[0, 0, 10, 10]])[0][0].id
    id2 = t.update([[1, 1, 11, 11]])[0][0].id  # high IoU → same track
    assert id1 == id2
    assert t.active == 1


def test_moved_far_creates_new_track():
    t = Tracker()
    id1 = t.update([[0, 0, 10, 10]])[0][0].id
    id2 = t.update([[100, 100, 110, 110]])[0][0].id  # no overlap → new track
    assert id1 != id2


def test_track_ages_out_after_max_misses():
    t = Tracker(max_misses=2)
    t.update([[0, 0, 10, 10]])
    assert t.active == 1
    for _ in range(3):  # 3 empty frames > max_misses(2)
        t.update([])
    assert t.active == 0


def test_two_faces_two_tracks():
    t = Tracker()
    visible = t.update([[0, 0, 10, 10], [100, 100, 110, 110]])
    assert len({trk.id for trk, _ in visible}) == 2
    assert t.active == 2


def test_greedy_assigns_highest_iou():
    t = Tracker()
    t.update([[0, 0, 10, 10]])  # track A near origin
    # next frame: a near-identical box and a far box; A must take the near one
    visible = t.update([[1, 1, 11, 11], [200, 200, 210, 210]])
    near = next(idx for trk, idx in visible if trk.age == 2)
    assert near == 0  # the high-IoU detection, not the far one
    assert t.active == 2  # plus a new track for the far box
