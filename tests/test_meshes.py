import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from organism_atlas import models
from organism_atlas.models import has_mesh, load_mesh, load_parts, mesh_credit, read_mesh_model
from organism_atlas.organs import ORGANS
from organism_atlas.render3d import look
from organism_atlas.render3d.primitives import E
from organism_atlas.render3d.scene import Scene3D

# источник анатомической модели каждого органа (см. models/mesh/ATTRIBUTION.md)
SOURCES = {
    "bp3d": {"stomach", "intestines", "kidneys", "heart", "brain", "pancreas", "adrenals", "esophagus", "rectum",
             "appendix", "trachea", "aorta", "vena_cava", "diaphragm", "pituitary", "thymus"},
    "hra": {"uterus", "ovaries", "bladder", "lymph_nodes"},
    "spl": {"thyroid"},
    "za": {"spinal_cord", "liver", "gallbladder", "lungs", "prostate", "spleen"},
}
ANATOMICAL = set().union(*SOURCES.values())
ATTRIBUTION = {"bp3d": ("BodyParts3D", "CC Attribution 4.0"), "hra": ("Human Reference Atlas", "CC Attribution 4.0"),
               "spl": ("Head and Neck", "3D Slicer License"), "za": ("Z-Anatomy", "CC Attribution-ShareAlike 4.0")}
TEXTURES = {"smooth", "lung", "gyri", "folia", "liver", "muscle", "gland", "bowel"}


def sphere(nu=96, nv=48):
    th = np.linspace(0, np.pi, nv + 1)
    ph = np.linspace(0, 2 * np.pi, nu, endpoint=False)
    V = np.array([[np.sin(t) * np.cos(p), np.sin(t) * np.sin(p), np.cos(t)] for t in th for p in ph])
    F = []
    for i in range(nv):
        for j in range(nu):
            a, b = i * nu + j, i * nu + (j + 1) % nu
            F += [[a, a + nu, b], [b, a + nu, b + nu]]
    return V, np.array(F)


class MeshFilesTests(unittest.TestCase):
    def test_expected_organs_have_meshes(self):
        self.assertEqual({k for k in ORGANS if has_mesh(k)}, ANATOMICAL)

    def test_meta_and_geometry(self):
        for key in ANATOMICAL:
            meta = read_mesh_model(key)
            src = next(s for s, keys in SOURCES.items() if key in keys)
            self.assertEqual(mesh_credit(key), src, key)
            for text in ATTRIBUTION[src]:
                self.assertIn(text, meta["attribution"], key)
            parts = load_mesh(key)
            self.assertEqual(len(parts), len(meta["groups"]), key)
            total = 0
            for p, g in zip(parts, meta["groups"]):
                where = "%s/%s" % (key, g["group"])
                self.assertRegex(p["color"], r"^#[0-9a-f]{6}$", where)
                self.assertIn(p["tex"], TEXTURES, where)
                V, F, N = p["v"], p["f"], p["vn"]
                self.assertTrue(np.isfinite(V).all() and np.isfinite(N).all(), where)
                self.assertGreaterEqual(F.min(), 0, where)
                self.assertLess(F.max(), len(V), where)
                self.assertEqual(len(F), g["triangles"], where)
                ln = np.linalg.norm(N, axis=1)
                self.assertTrue(np.allclose(ln, 1, atol=0.01), where)
                self.assertFalse(V.flags.writeable, where)        # общий кэш защищён от записи
                total += len(F)
            self.assertLess(total, 100_000, key)

    def test_faces_point_outward(self):
        """нормали граней смотрят наружу: иначе отсечение задних граней проделает дыры"""
        for key in ANATOMICAL:
            for p in load_mesh(key):
                V, F = p["v"], p["f"]
                fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
                agree = ((fn * p["vn"][F].mean(1)).sum(1) > 0).mean()
                self.assertGreater(agree, 0.95, (key, p["color"]))


class MeshRenderTests(unittest.TestCase):
    def test_rasterizer_matches_analytic_sphere(self):
        V, F = sphere()
        mesh = {"k": "m", "v": V, "f": F, "vn": V, "color": "#c04040", "tex": "smooth", "gloss": 0.4}
        for st in ("classic", "realistic"):
            a = np.asarray(Scene3D([E((0, 0, 0), (1, 1, 1), "#c04040")]).render(200, 200, -62, 18, style=st,
                                                                                 shadows=False)).astype(int)
            b = np.asarray(Scene3D([mesh]).render(200, 200, -62, 18, style=st, shadows=False)).astype(int)
            self.assertLess((np.abs(a - b).max(-1) > 12).mean(), 0.003, st)

    def test_every_anatomical_organ_renders(self):
        for key in ANATOMICAL:
            im = np.asarray(Scene3D(load_parts(key)).render(160, 120, -62, 18, ss=1))
            fg = (np.abs(im.astype(int) - im[0, 0].astype(int)).max(-1) > 25).mean()
            self.assertGreater(fg, 0.05, key)                       # орган занимает заметную часть кадра

    def test_mesh_casts_shadows(self):
        sc = Scene3D(load_parts("heart"))
        on = np.asarray(sc.render(160, 120, -62, 18, shadows=True)).astype(int).sum()
        off = np.asarray(sc.render(160, 120, -62, 18, shadows=False)).astype(int).sum()
        self.assertLess(on, off)


class FallbackTests(unittest.TestCase):
    def test_procedural_when_switched_off(self):
        lk = dict(look.get(), models="procedural")
        with mock.patch.object(look, "get", return_value=lk):
            self.assertEqual(load_parts("heart")[0]["k"], "e")

    def test_broken_mesh_falls_back_to_procedural(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = read_mesh_model("heart")
            Path(tmp, "heart.json").write_text(json.dumps(meta), encoding="utf-8")
            Path(tmp, meta["mesh"]).write_bytes(b"not a zip")
            with mock.patch.object(models, "_mesh_dir", return_value=Path(tmp)), \
                    mock.patch.dict(models._mesh_cache, clear=True), mock.patch("sys.stderr"):
                parts = load_parts("heart")
        self.assertTrue(all(p["k"] in ("e", "t") for p in parts))

    def test_negative_vertex_index_is_rejected(self):
        """отрицательный номер вершины numpy молча взял бы с конца, а видеокарта - за пределами буфера"""
        with tempfile.TemporaryDirectory() as tmp:
            meta = read_mesh_model("heart")
            Path(tmp, "heart.json").write_text(json.dumps(meta), encoding="utf-8")
            with np.load(models._mesh_dir() / meta["mesh"]) as z:
                arrays = {k: z[k] for k in z.files}
            arrays["f0"] = arrays["f0"].astype(np.int64)
            arrays["f0"].flat[0] = -1
            np.savez(Path(tmp, meta["mesh"]), **arrays)
            with mock.patch.object(models, "_mesh_dir", return_value=Path(tmp)), \
                    mock.patch.dict(models._mesh_cache, clear=True):
                with self.assertRaisesRegex(ValueError, "за пределами"):
                    models.load_mesh("heart")

    def test_organs_without_mesh_use_procedural(self):
        for key in set(ORGANS) - ANATOMICAL:
            self.assertTrue(all(p["k"] in ("e", "t") for p in load_parts(key)), key)


if __name__ == "__main__":
    unittest.main()
