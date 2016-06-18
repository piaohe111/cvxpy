"""
Copyright 2016 Jaehyun Park

This file is part of CVXPY.

CVXPY is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

CVXPY is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with CVXPY.  If not, see <http://www.gnu.org/licenses/>.
"""

import cvxpy.interface as intf
import cvxpy.settings as s
from cvxpy.problems.solvers.solver import Solver
import cvxpy.utilities as u
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as SLA

class LS(Solver):
    """An interface for the ECOS solver.
    """

    # Solver capabilities.
    # Incapable of solving any general cone program,
    # must be invoked through a special path.
    LP_CAPABLE = False
    SOCP_CAPABLE = False
    SDP_CAPABLE = False
    EXP_CAPABLE = False
    MIP_CAPABLE = False

    def import_solver(self):
        """Imports the solver.
        """
        import ls

    def name(self):
        """The name of the solver.
        """
        return s.LS

    def matrix_intf(self):
        """The interface for matrices passed to the solver.
        """
        return intf.DEFAULT_SPARSE_INTF

    def vec_intf(self):
        """The interface for vectors passed to the solver.
        """
        return intf.DEFAULT_INTF

    def split_constr(self, constr_map):
        """Extracts the equality, inequality, and nonlinear constraints.

        Parameters
        ----------
        constr_map : dict
            A dict of the canonicalized constraints.

        Returns
        -------
        tuple
            (eq_constr, ineq_constr, nonlin_constr)
        """
        return (constr_map[s.EQ], constr_map[s.LEQ], [])

    def suitable(self, prob):
        """Temporary method to determine whether the given Problem object is suitable for LS solver.
        """
        import cvxpy.constraints.eq_constraint as eqc

        import cvxpy.expressions.variables as var
        allowedVariables = (var.variable.Variable, var.symmetric.SymmetricUpperTri)
        
        return (prob.is_dcp() and prob.objective.args[0].is_quadratic()
            and not prob.objective.args[0].is_affine()
            and all([isinstance(c, eqc.EqConstraint) for c in prob.constraints])
            and all([type(v) in allowedVariables for v in prob.variables()])
            and all([not v.domain for v in prob.variables()]) # no implicit variable domains (TODO: domains are not implemented yet)
            )

    def get_sym_data(self, objective, constraints, cached_data=None):
        class FakeSymData(object):
            def __init__(self, objective, constraints):
                self.constr_map = {s.EQ: constraints}
                vars_ = objective.variables()
                for c in constraints:
                    vars_ += c.variables()
                vars_ = list(set(vars_))
                self.var_offsets, self.var_sizes, self.x_length = self.get_var_offsets(vars_)
            
            def get_var_offsets(self, variables):
                var_offsets = {}
                var_sizes = {}
                vert_offset = 0
                for x in variables:
                    var_sizes[x.id] = x.size
                    var_offsets[x.id] = vert_offset
                    vert_offset += x.size[0]*x.size[1]

                return (var_offsets, var_sizes, vert_offset)
        return FakeSymData(objective, constraints)

    def solve(self, objective, constraints, sym_data):
        """Returns the result of the call to the solver.

        Parameters
        ----------
        objective : CVXPY objective object
            Raw objective passed by CVXPY. Can be convex/concave.
        constraints : list
            The list of raw constraints.
        
        Returns
        -------
        tuple
            (status, optimal value, primal, equality dual, inequality dual)
        """

        id_map = sym_data.var_offsets
        N = sym_data.x_length

        #import time

        #ts = [time.time()]

        M = u.quad_coeffs(objective.args[0], id_map, N)[0].tocsr()

        #ts.append(time.time())

        P = M[:N, :N]
        q = (M[:N, N] + M[N, :N].transpose())/2
        q = q.todense()
        r = M[N, N]

        #ts.append(time.time())

        if len(constraints) > 0:
            Cs = [u.affine_coeffs(c._expr, id_map, N) for c in constraints]
            As = sp.vstack([C[0] for C in Cs])
            bs = np.vstack([C[1] for C in Cs])
            m = bs.shape[0]
            AA = sp.bmat([[P, As.transpose()], [As, None]])
            BB = np.vstack([-q, -bs])
        else: # avoiding calling vstack with empty list
            AA = P
            BB = -q

        #ts.append(time.time())

        try:
            BB = SLA.spsolve(AA.tocsr(), BB)
            x = np.array(BB[:N])
            nu = np.array(BB[N:])
            s = np.dot(x.transpose(), P*x)
            t = np.dot(q.transpose(), x)
            p_star = (s+2*t)[0, 0] + r

        except ArithmeticError:
            x = None
            nu = None
            p_star = None

        #ts.append(time.time())

        #print ("runtime break: ")
        #print ([ts[i+1]-ts[i] for i in range(len(ts)-1)])

        return self.format_results(x, nu, p_star)

    def format_results(self, x, nu, p_star):
    #def format_results(self, results_dict, data, cached_data):
        """Converts the solver output into standard form.

        Parameters
        ----------
        results_dict : dict
            The solver output.
        data : dict
            Information about the problem.
        cached_data : dict
            A map of solver name to cached problem data.

        Returns
        -------
        dict
            The solver output in standard form.
        """
        new_results = {}
        if x is not None: # just for now
            new_results[s.VALUE] = p_star
            new_results[s.STATUS] = s.OPTIMAL
            new_results[s.PRIMAL] = x
            new_results[s.EQ_DUAL] = nu
        else:
            new_results[s.STATUS] = s.INFEASIBLE
        return new_results
