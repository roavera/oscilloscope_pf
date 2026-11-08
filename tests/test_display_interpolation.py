"""Pruebas sin dependencias gráficas: ejecutar desde la raíz del repositorio."""
import unittest
import numpy as np
from gui.display_interpolation import interpolate_display, MODES


class TestDisplayInterpolation(unittest.TestCase):
    def test_modos_disponibles(self):
        self.assertEqual(MODES, ("none", "linear", "cubic", "sinc"))

    def test_lineal_conserva_muestras(self):
        x=np.arange(5)*1e-4
        y=np.array([0.,1.,0.,-1.,0.])
        for mode in ("none", "linear"):
            xo,yo=interpolate_display(x,y,mode)
            np.testing.assert_array_equal(xo,x)
            np.testing.assert_array_equal(yo,y)

    def test_cubica_conserva_muestras_originales(self):
        x=np.linspace(0,1,15); y=np.sin(2*np.pi*x)
        xo,yo=interpolate_display(x,y,"cubic",max_factor=4)
        np.testing.assert_allclose(xo[::4],x,rtol=0,atol=1e-14)
        np.testing.assert_allclose(yo[::4],y,rtol=0,atol=1e-14)

    def test_cubica_monotona_sin_sobreoscilacion(self):
        x=np.array([0.,.1,.4,.8,1.]); y=np.array([0.,0.,.1,.3,1.])
        _,yo=interpolate_display(x,y,"cubic")
        self.assertTrue(np.all(np.diff(yo)>=-1e-12))
        self.assertGreaterEqual(yo.min(),y.min()-1e-12)
        self.assertLessEqual(yo.max(),y.max()+1e-12)

    def test_cubica_no_uniforme_roll(self):
        x=np.array([0.,.1,.3,.8,1.]);y=np.cos(x)
        xo,yo=interpolate_display(x,y,"cubic",max_factor=4)
        np.testing.assert_allclose(xo[::4],x,atol=1e-14)
        np.testing.assert_allclose(yo[::4],y,atol=1e-14)

    def test_sinc_conserva_dc_y_muestras(self):
        x=np.arange(70)/97656.25;y=np.ones(70)*2.75
        xo,yo=interpolate_display(x,y,"sinc",max_factor=4)
        np.testing.assert_allclose(yo,2.75,atol=1e-10)
        np.testing.assert_allclose(yo[::4],y,atol=0)
        np.testing.assert_allclose(xo[::4],x,atol=1e-15)

    def test_sinc_senoidal_baja_frecuencia(self):
        x=np.arange(120)/97656.25
        y=np.sin(2*np.pi*3000*x)
        xo,yo=interpolate_display(x,y,"sinc",max_factor=4)
        trim=(xo>x[9])&(xo<x[-10])
        self.assertLess(np.max(np.abs(yo[trim]-np.sin(2*np.pi*3000*xo[trim]))),.03)

    def test_sinc_no_uniforme_sin_inventar_muestras(self):
        x=np.array([0.,.1,.2,.33,.4]); y=np.arange(5.)
        xo,yo=interpolate_display(x,y,"sinc")
        np.testing.assert_array_equal(xo,x)
        np.testing.assert_array_equal(yo,y)

    def test_entrada_no_se_modifica(self):
        x=np.arange(8.);y=np.array([1.,2.,3.,2.,1.,4.,-2.,1.])
        a,b=x.copy(),y.copy()
        for m in MODES:interpolate_display(x,y,m)
        np.testing.assert_array_equal(x,a)
        np.testing.assert_array_equal(y,b)

    def test_limite_puntos(self):
        x=np.arange(1000.)
        for m in ("cubic","sinc"):
            xo,yo=interpolate_display(x,np.sin(x),m,max_points=2048)
            self.assertLessEqual(len(xo),2048)
            self.assertEqual(len(xo),len(yo))

    def test_dos_muestras_cubica_es_lineal(self):
        x=np.array([0.,1.]);y=np.array([2.,4.])
        xo,yo=interpolate_display(x,y,"cubic",max_factor=4)
        np.testing.assert_allclose(yo,2+2*xo)

    def test_input_invalido(self):
        with self.assertRaises(ValueError):interpolate_display([1,0],[1,2],"cubic")
        with self.assertRaises(ValueError):interpolate_display([0,1],[1,np.nan],"sinc")
        with self.assertRaises(ValueError):interpolate_display([0,1],[1,2],"hermite")


if __name__ == "__main__":unittest.main()
