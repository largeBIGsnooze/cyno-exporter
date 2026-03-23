import os, json, re
from utils.plugins import Gr2ToJson
from typing import Any 

class Wavefront:
    @staticmethod   
    def from_gr2_json(file_path: str) -> list[Any]: 
        data = []
        with open(f"{file_path}.gr2_json", "r") as f:
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
    def to_obj(file_path: str) -> None:
        Gr2ToJson().run(file_path) 
        meshes = Wavefront.from_gr2_json(file_path)

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

        with open(f"{file_path.replace('.gr2', '')}.obj", "w") as f:
            f.write("\n".join(plaintext))

        os.remove(file_path) 
        os.remove(f"{file_path}.gr2_json")

    @staticmethod
    def o(name: str) -> str:
        return f"o {name}"

    @staticmethod
    def v(*v: Any) -> str:
        return f"v {' '.join(map(str, *v))}"

    @staticmethod
    def vn(*n: Any) -> str: 
        return f"vn {' '.join(map(str, *n))}"

    @staticmethod
    def vt(*vt: Any) -> str:
        return f"vt {' '.join(map(str, *vt))}"

    @staticmethod
    def usemtl(mtl: str) -> str:
        return f"usemtl {mtl}"

    @staticmethod
    def s() -> str:
        return f"s 1" 

    @staticmethod
    def f(v1: int, v2: int, v3: int) -> str:
        return f"f {v1}/{v1}/{v1} {v2}/{v2}/{v2} {v3}/{v3}/{v3}"
