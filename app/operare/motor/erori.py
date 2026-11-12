"""Excepțiile motorului. Fără dependențe: se importă de oriunde (pașii, testele, panoul)."""


class EroareMotor(Exception):
    """Baza erorilor motorului."""


class EroareTemporara(EroareMotor):
    """Merită reîncercată (rețea, limită de rată, eroare de server): pasul o reia cu pauză crescătoare."""


class EroareDefinitiva(EroareMotor):
    """Nu are sens reîncercarea. Jobul ajunge direct în coada de erori."""


class EroareAutentificare(EroareDefinitiva):
    """Eroare de autentificare la un conector: canalul se pune pe pauză și se cere reautorizare (7.5)."""


class ArgumentNepermis(ValueError):
    """Un flux sau un pas a primit conținut în loc de identificatori (vezi `argumente`)."""


class MotorOprit(EroareMotor):
    """Operația cere executorul, dar acest proces nu l-a pornit (procesul web doar pune în coadă)."""
