"""Costurile estimate ale tipurilor de livrabil, ca DATE de pornire (migrarea `0020`; după aceea se
editează în tabelul `planificare_costuri`). Pe fiecare tip: cererile și tokenii așteptați pe profil de
sarcină (8.2) și minutele de CPU pe culoar greu. Toate sunt ESTIMĂRI nemăsurate; se recalibrează din
jurnalul de apeluri după primele luni de producție."""

# tip -> ({profil: {"apeluri": n, "tokeni": n}}, minute de CPU pe culoar greu)
COSTURI_IMPLICITE: dict[str, tuple[dict[str, dict[str, int]], float]] = {
    "postare": ({"creatie": {"apeluri": 2, "tokeni": 4000}, "rescriere": {"apeluri": 1, "tokeni": 2500},
                 "judecata": {"apeluri": 3, "tokeni": 9000}}, 0.0),
    "articol": ({"strategie": {"apeluri": 1, "tokeni": 6000}, "creatie": {"apeluri": 4, "tokeni": 16000},
                 "judecata": {"apeluri": 3, "tokeni": 12000}}, 0.0),
    "video": ({"creatie": {"apeluri": 3, "tokeni": 8000}, "rescriere": {"apeluri": 1, "tokeni": 2000},
               "judecata": {"apeluri": 3, "tokeni": 9000}}, 25.0),
    "imagine": ({"creatie": {"apeluri": 1, "tokeni": 1500}, "judecata": {"apeluri": 2, "tokeni": 4000}}, 4.0),
    "reclama": ({"creatie": {"apeluri": 2, "tokeni": 3500}, "judecata": {"apeluri": 3, "tokeni": 8000}}, 0.0),
    "_implicit": (
        {"creatie": {"apeluri": 2, "tokeni": 4000}, "judecata": {"apeluri": 2, "tokeni": 6000}}, 0.0
    ),
}  # fmt: skip
