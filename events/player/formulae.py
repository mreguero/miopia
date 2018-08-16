import pyknow
import builtins
import types
from pyknow import MATCH, NE, Fact, NOT, OR, AND, TEST
import ast
import _ast
import sys

pyknow.watch('RULES', 'FACTS')


class NameExtractor(ast.NodeVisitor):
    def visit_Attribute(self, node):
        name = ".".join([list(self.visit(node.value))[0], node.attr])
        return set([name])

    def visit_Name(self, node):
        return set([node.id])

    def generic_visit(self, node):
        """Called if no explicit visitor function exists for a node."""
        acc = set()
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        val = self.visit(item)
                        if val:
                            acc |= val
            elif isinstance(value, ast.AST):
                val = self.visit(value)
                if val:
                    acc |= val
        return acc


def source_validator(n):
    return n in ['any', 'ext', 'int']


class Dependency(pyknow.Fact):
    name = pyknow.Field(str, mandatory=True)
    needs = pyknow.Field(str, mandatory=True)
    source = pyknow.Field(source_validator, default='any')


class Formulae(pyknow.Fact):
    lhs = pyknow.Field(str, mandatory=True)
    op = pyknow.Field(str, mandatory=True, default='=')
    rhs = pyknow.Field([str], mandatory=True, default=[])
    code = pyknow.Field(types.CodeType, mandatory=True)


class FormulaSolver(pyknow.KnowledgeEngine):
    @pyknow.DefFacts()
    def load_builtins(self,):
        for name in builtins:
            yield Fact(is_builtin=name)

    @pyknow.DefFacts()
    def load_code(self, code, filename, builtins=tuple(dir(builtins))):
        module = ast.parse(code)
        assigns = module.body
        dependencies = dict()

        for assign in assigns:
            tassign = type(assign)
            if tassign == ast.Assign:
                assert len(assign.targets) == 1, "Only one target per assignment allowed"
                op = '='
                target = assign.targets[0]
            elif tassign == ast.AugAssign:
                op = '+'
                target = assign.target
            elif tassign == ast.DecAssign:
                op = '-'
                target = assign.target
            else:
                raise TypeError("Only =, +=, -= assigns are allowed.")

            lhs = list(NameExtractor().visit(target))[0]
            rhs = list(NameExtractor().visit(assign.value))
            try:
                code = compile(ast.Expression(assign.value), filename,
                               mode='eval')
            except Exception as exc:
                raise SyntaxError(
                    "Compilation error. %r" % ast.dump(assign)) from exc

            # yield Formulae(lhs=lhs, rhs=rhs, op=op, code=code)
            for dep in rhs:
                if dep not in builtins:
                    if op == '=' and lhs != dep:
                        source = 'any'
                    else:
                        source = 'db'
                    yield Dependency(name=lhs, needs=dep, source=source)

    @pyknow.Rule(
        Dependency(name=MATCH.name, needs=MATCH.dep),
        NOT(
            Dependency(name=MATCH.dep)))
    def name_is_final(self, name):
        # TODO: Retrieve value from db.
        value = int(random.rand() * 1000)
        self.declare(Solved(name=name, value=value, source='db'))

    # @pyknow.Rule(
    #     Formulae(lhs=MATCH.name))
    # def is_calculated(self, name):
    #     self.declare(Fact(is_calculated=name))

    # @pyknow.Rule(
    #     Formulae(rhs=MATCH.names))
    # def is_needed(self, names):
    #     for name in names:
    #         self.declare(Fact(is_needed=name))

#     @pyknow.Rule(
#         Fact(is_needed=MATCH.name),
#         NOT(
#             Fact(is_calculated=MATCH.name),
#             Fact(is_builtin=MATCH.name)))
#     def is_missing(self, name):
#         self.declare(Fact(is_missing=name))

#     @pyknow.Rule(
#         OR(
#             AND(
#                 Formulae(op='=', lhs=MATCH.name, rhs=MATCH.names),
#                 TEST(lambda name, names: name in names)),
#             Formulae(op=NE('='), lhs=MATCH.name)))
#     def autoref_formula(self, name):
#         """A formula is updating a name which is referenced inside the
#         formula."""
#         self.declare(Fact(is_missing=name))

#     @pyknow.Rule(
#         Fact(is_missing=MATCH.name))
#     def obtain_missing_datum(self, name):
#         self.dataproxy[name]

if __name__ == "__main__":
    with open(sys.argv[1], 'r') as codefile:
        solver = FormulaSolver()
        solver.reset(code=codefile.read(), filename=sys.argv[1])
        solver.run()
