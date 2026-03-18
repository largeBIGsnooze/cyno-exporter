import os, json, re
from utils.plugins import Gr2ToJson


class Wavefront:
    @staticmethod
    def from_gr2_json(obj):
        data = []
        with open(f"{obj}.gr2_json", "r") as f:
            gr2_json = json.loads(re.sub(r"\-nan\(ind\)|\-inf|inf", "0", f.read()))

        for mesh in gr2_json["meshes"]:
            vertex = mesh["vertex"]
            data.append(
                {
                    "name": mesh["name"],
                    "position": vertex["position"],
                    "tangent": vertex.get("tangent", []),  # unsupported
                    "normal": vertex.get("normal", []),
                    "texcoord0": vertex["texcoord0"],
                    "indices": [
                        {"name": i["name"], "faces": i["faces"]}
                        for i in mesh["indices"]
                    ],
                } 
            )
        return data

    @staticmethod
    def to_obj(gr2_json):
        Gr2ToJson().run(gr2_json)
        meshes = Wavefront.from_gr2_json(gr2_json)

        plaintext = []
        model_offset = 1

        for mesh in meshes:
            plaintext.append(Wavefront.o(mesh["name"]))

            for i in range(0, len(mesh["position"]), 3):
                plaintext.append(Wavefront.v(mesh["position"][i : i + 3]))

            for i in range(0, len(mesh["texcoord0"]), 2):
                plaintext.append(Wavefront.vt(mesh["texcoord0"][i : i + 2]))

            if mesh["normal"]:
                for i in range(0, len(mesh["normal"]), 3):
                    plaintext.append(Wavefront.vn(mesh["normal"][i : i + 3]))

            plaintext.append(Wavefront.s())

            for indice in mesh["indices"]:
                plaintext.append(Wavefront.usemtl(indice["name"]))
                faces = indice["faces"]
                texcoords = mesh["texcoord0"]
                for i in range(0, len(faces), 3):
                    v1 = faces[i] + model_offset
                    v2 = faces[i + 1] + model_offset
                    v3 = faces[i + 2] + model_offset
                    plaintext.append(
                        Wavefront.f(
                            v1=v1,
                            v2=v2,
                            v3=v3,
                        )
                    )

            model_offset += len(mesh["position"]) // 3

        with open(f"{gr2_json.replace('.gr2', '')}.obj", "w") as f:
            f.write("\n".join(plaintext))

        os.remove(gr2_json)
        os.remove(f"{gr2_json}.gr2_json")

    @staticmethod
    def o(name):
        return f"o {name}"

    @staticmethod
    def v(*v):
        return f"v {' '.join(map(str, *v))}"

    @staticmethod
    def vn(*n):
        return f"vn {' '.join(map(str, *n))}"

    @staticmethod
    def vt(*vt):
        return f"vt {' '.join(map(str, *vt))}"

    @staticmethod
    def usemtl(mtl):
        return f"usemtl {mtl}"

    @staticmethod
    def s():
        return f"s 1"

    @staticmethod
    def f(v1, v2, v3):
        return f"f {v1}/{v1}/{v1} {v2}/{v2}/{v2} {v3}/{v3}/{v3}"
