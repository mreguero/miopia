from collections import defaultdict
from functools import singledispatch
import ast
import _ast as astype
import operator as op
import sys

import pythonflow as pf


FUNCTIONS = {
    'MIN': min,
    'MAX': max,
    'pick_next': lambda xs: xs.pop()}


class LazySymbol(pf.Operation):
    def __init__(self, target, graph, **kwargs):
        self.t_exp = target
        self.t_sym = '_' + target
        self.graph_ops = graph.operations
        if self.t_sym not in self.graph_ops:
            pf.placeholder(self.t_sym)
        super(LazySymbol, self).__init__(**kwargs)

    def evaluate(self, context, callback=None):
        if self.t_exp in self.graph_ops:
            return self.graph_ops[self.t_exp].evaluate(context, callback)
        else:
            return self.graph_ops[self.t_sym].evaluate(context, callback)


class Resolver:
    def __init__(self, keys, graph):
        self.keys = keys
        self.graph = graph

    def __contains__(self, name):
        return name in self.keys

    def __call__(self, fetches, **placeholders):
        vs = {'_' + k: v for k, v in placeholders.items()}

        with self.graph:
            for key in vs:
                if key not in self.graph.operations:
                    pf.placeholder(key)

        return self.graph(fetches, **vs)


@singledispatch
def resolve_name(name):
    raise TypeError('Unknown type %r' % (type(x), ))


@resolve_name.register(astype.Attribute)
def _(x):
    return '.'.join([resolve_name(x.value), x.attr])


@resolve_name.register(astype.Name)
def _(x):
    return x.id


@singledispatch
def unwind(x, lhs=None, graph=None):
    raise TypeError('Unknown type %r' % (type(x), ))


@unwind.register(astype.Module)
def _(mod, graph=None):
    keys = list()
    for entry in mod.body:
        keys.append(unwind(entry, graph=graph))
    return keys


@unwind.register(astype.Assign)
def _(ass, graph=None):
    [lhs], rhs = ass.targets, ass.value

    lhs_name = resolve_name(lhs)
    unwind(rhs, lhs=lhs_name, graph=graph).set_name(lhs_name)

    return lhs_name


@unwind.register(astype.AugAssign)
def _(ass, graph=None):
    lhs, rhs = ass.target, ass.value

    lhs_name = resolve_name(lhs)

    phname = '_' + lhs_name
    if phname not in graph.operations:
        old = pf.placeholder(phname)
    else:
        old = ops[phname]

    (old + unwind(rhs, lhs=lhs_name, graph=graph)).set_name(lhs_name)

    return lhs_name


@unwind.register(astype.Call)
def _(call, lhs=None, graph=None):
    global FUNCTIONS
    fn = FUNCTIONS[resolve_name(call.func)]
    args = unwind(call.args, lhs=lhs, graph=graph)
    return pf.func_op(fn, *args)


@unwind.register(astype.Name)
@unwind.register(astype.Attribute)
def _(x, lhs=None, graph=None):
    name = resolve_name(x)
    if name.startswith('_'):
        if name in graph.operations:
            return graph.operations[name]
        else:
            return pf.placeholder(name)
    elif lhs == name:
        name = '_' + name
        if name in graph.operations:
            return graph.operations[name]
        else:
            return pf.placeholder(name)
    else:
        return LazySymbol(name, graph=graph)


@unwind.register(list)
def _(xs, lhs=None, graph=None):
    return [unwind(x, lhs=lhs, graph=graph) for x in xs]


@unwind.register(astype.BinOp)
def _(foo, lhs=None, graph=None):
    left = unwind(foo.left, lhs=lhs, graph=graph)
    right = unwind(foo.right, lhs=lhs, graph=graph)
    op = unwind(foo.op, lhs=lhs, graph=graph)
    return pf.func_op(op, left, right)

@unwind.register(astype.Compare)
def _(foo, lhs=None, graph=None):
    left = unwind(foo.left, lhs=lhs, graph=graph)
    ops = unwind(foo.ops, lhs=lhs, graph=graph)
    comparators = unwind(foo.comparators, lhs=lhs, graph=graph)

    def generate_comparisons():
        comparisons = zip(ops, zip([left] + comparators, comparators))
        for (con, (lft, rht)) in comparisons:
            yield pf.func_op(con, lft, rht)

    return pf.all_(list(generate_comparisons()))


@unwind.register(astype.Sub)
def _(_, lhs=None, graph=None):
    return op.sub

@unwind.register(astype.LtE)
def _(_, lhs=None, graph=None):
    return op.le

@unwind.register(astype.Lt)
def _(_, lhs=None, graph=None):
    return op.lt

@unwind.register(astype.GtE)
def _(_, lhs=None, graph=None):
    return op.ge

@unwind.register(astype.Gt)
def _(_, lhs=None, graph=None):
    return op.gt

@unwind.register(astype.Div)
def _(_, lhs=None, graph=None):
    return op.sub

@unwind.register(astype.Add)
def _(_, lhs=None, graph=None):
    return op.add


@unwind.register(astype.Mult)
def _(_, lhs=None, graph=None):
    return op.mul


@unwind.register(astype.Num)
def _(num, lhs=None, graph=None):
    return pf.constant(num.n)


@unwind.register(astype.Str)
def _(st, lhs=None, graph=None):
    return pf.constant(st.s)


# tree -> (**placeholders -> {name: value})
def a2r(tree, graph):
    return Resolver(unwind(tree, graph=graph), graph)


def generate_graph(filename):
    # Generate AST
    with open(filename, 'r') as fp:
        tree = ast.parse(fp.read())

    # AST -> Graph
    with pf.Graph() as graph:
        return a2r(tree, graph)

if __name__ == '__main__':
    db_status = {
        'player.mod_living_space': 10,
        'player.military_population': 20,
        'player.peasants_hourly_change': 30,
        'player.peasants': 5,
        'player.gold': 20,
        'player.net_income': 10,
        'player.food': 30,
        'player.food_remaining': 30,
        'player.offensive_specialists': 30,
        'player.offensive_specialists_in_progress': [0,10],
        'player.defensive_specialists': 30,
        'player.defensive_specialists_in_progress': [0,10],
        'player.elites': 30,
        'player.barren_land': 30,
        'player.homes': 30,
        'mod_off': 20,
        'dst.mod_def': 20,
        'player.homes_in_progress': [30],
        'player.barren_land_in_progress': [30, 40],
        'player.elites_in_progress': [0,10],
    }

    resolver = generate_graph(sys.argv[1])

    for key in resolver.keys:
        print(key, '=', resolver(key, **db_status))
