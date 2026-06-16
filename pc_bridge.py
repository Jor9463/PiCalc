# pc_bridge.py mock for CPython testing

_evaluar_expr = None
_decimal_frac = None
_vars_actuales = None
_extraer_nums = None
_matrices_ref = None

def registrar(evaluar_fn, decimal_fn, variables_fn, extraer_fn, matrices_dict):
    global _evaluar_expr, _decimal_frac, _vars_actuales, _extraer_nums, _matrices_ref
    _evaluar_expr = evaluar_fn; _decimal_frac = decimal_fn
    _vars_actuales = variables_fn; _extraer_nums = extraer_fn
    _matrices_ref = matrices_dict

def evaluar_expresion(e, v=None): return _evaluar_expr(e, v)
def decimal_a_fraccion(v): return _decimal_frac(v)
def variables_actuales(e=None): return _vars_actuales(e)
def extraer_numeros(c, l): return _extraer_nums(c, l)
def get_matrices(): return _matrices_ref
