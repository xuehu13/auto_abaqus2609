#include <CGAL/Periodic_3_mesh_3/config.h>
#include <CGAL/Random.h>

#include <CGAL/Exact_predicates_inexact_constructions_kernel.h>
#include <CGAL/make_periodic_3_mesh_3.h>
#include <CGAL/Periodic_3_mesh_triangulation_3.h>
#include <CGAL/Periodic_3_function_wrapper.h>
#include <CGAL/Periodic_3_mesh_3/IO/File_medit.h>

#include <CGAL/Labeled_mesh_domain_3.h>
#include <CGAL/Mesh_domain_with_polyline_features_3.h>
#include <CGAL/Mesh_complex_3_in_triangulation_3.h>
#include <CGAL/Mesh_criteria_3.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <list>
#include <string>
#include <vector>
#include <unordered_map>
#include <sstream>
#include <stdexcept>
#include "expression_parser.hpp"


// ============================================================
// CGAL types
// ============================================================

using K =
    CGAL::Exact_predicates_inexact_constructions_kernel;

using FT =
    K::FT;

using Point =
    K::Point_3;

using Iso_cuboid =
    K::Iso_cuboid_3;

using Function =
    FT(const Point&);

using Periodic_function =
    CGAL::Periodic_3_function_wrapper<
        Function,
        K
    >;

using Base_domain =
    CGAL::Labeled_mesh_domain_3<K>;

using Periodic_mesh_domain =
    CGAL::Mesh_domain_with_polyline_features_3<
        Base_domain
    >;

using Polyline =
    std::vector<Point>;

using Polylines =
    std::list<Polyline>;

using Tr =
    CGAL::Periodic_3_mesh_triangulation_3<
        Periodic_mesh_domain
    >::type;

using C3t3 =
    CGAL::Mesh_complex_3_in_triangulation_3<
        Tr,
        Periodic_mesh_domain::Corner_index,
        Periodic_mesh_domain::Curve_index
    >;

using Periodic_mesh_criteria =
    CGAL::Mesh_criteria_3<Tr>;

namespace params =
    CGAL::parameters;


// ============================================================
// Runtime case configuration
// ============================================================

// The implicit equation and CGAL sizing parameters are read from
// cgal_case.txt.  Therefore a new surface does not require recompilation.
double L = 10.0;
constexpr double TOL = 1.0e-9;
Expression SURFACE_EXPRESSION;

struct RuntimeConfig
{
    double L = 10.0;
    std::string expression;
    double edge_size = 0.18;
    double facet_angle = 25.0;
    double facet_size = 0.15;
    double facet_distance = 0.03;
    double cell_radius_edge_ratio = 2.0;
    double cell_size = 0.50;
    unsigned int random_seed = 20260911;
};

std::string trim(const std::string& s)
{
    const auto a = s.find_first_not_of(" \t\r\n");
    if (a == std::string::npos) return "";
    const auto b = s.find_last_not_of(" \t\r\n");
    return s.substr(a, b - a + 1);
}

bool read_runtime_config(const std::string& filename, RuntimeConfig& c)
{
    std::ifstream in(filename);
    if (!in) return false;
    std::unordered_map<std::string, std::string> kv;
    std::string line;
    while (std::getline(in, line))
    {
        line = trim(line);
        if (line.empty() || line[0] == '#') continue;
        const auto eq = line.find('=');
        if (eq == std::string::npos) continue;
        kv[trim(line.substr(0, eq))] = trim(line.substr(eq + 1));
    }
    try
    {
        c.L = std::stod(kv.at("L"));
        c.expression = kv.at("expression");
        c.edge_size = std::stod(kv.at("edge_size"));
        c.facet_angle = std::stod(kv.at("facet_angle"));
        c.facet_size = std::stod(kv.at("facet_size"));
        c.facet_distance = std::stod(kv.at("facet_distance"));
        c.cell_radius_edge_ratio = std::stod(kv.at("cell_radius_edge_ratio"));
        c.cell_size = std::stod(kv.at("cell_size"));
        c.random_seed = static_cast<unsigned int>(std::stoul(kv.at("random_seed")));
    }
    catch (const std::exception&)
    {
        return false;
    }
    return c.L > 0.0 && !c.expression.empty();
}

FT surface_function(const Point& p)
{
    const double s = 2.0 * CGAL_PI / L;
    const double X = CGAL::to_double(p.x()) * s;
    const double Y = CGAL::to_double(p.y()) * s;
    const double Z = CGAL::to_double(p.z()) * s;
    return SURFACE_EXPRESSION.eval(X, Y, Z);
}


// ============================================================
// Feature input
// ============================================================

struct FeatureMetadata
{
    int face_id;
    int closed;
    int start_class;
    int end_class;
    int n_points;
};


bool read_features(
    const std::string& filename,
    Polylines& polylines,
    std::vector<FeatureMetadata>& metadata
)
{
    std::ifstream in(
        filename
    );

    if (!in)
    {
        return false;
    }


    int n_curves = 0;

    in >> n_curves;


    if (
        !in
        ||
        n_curves <= 0
    )
    {
        return false;
    }


    for (
        int curve_id = 0;
        curve_id < n_curves;
        ++curve_id
    )
    {
        FeatureMetadata meta;


        in
            >> meta.face_id
            >> meta.closed
            >> meta.start_class
            >> meta.end_class
            >> meta.n_points;


        if (
            !in
            ||
            meta.n_points < 2
        )
        {
            return false;
        }


        Polyline polyline;

        polyline.reserve(
            static_cast<std::size_t>(
                meta.n_points
            )
        );


        for (
            int i = 0;
            i < meta.n_points;
            ++i
        )
        {
            double x;
            double y;
            double z;

            in
                >> x
                >> y
                >> z;


            if (!in)
            {
                return false;
            }


            polyline.emplace_back(
                x,
                y,
                z
            );
        }


        polylines.push_back(
            polyline
        );

        metadata.push_back(
            meta
        );
    }


    return true;
}


// ============================================================
// Can a set of three coordinates be translated by k*L
// into [0,L] using ONE integer k?
//
// If yes, the triangle does not require geometric clipping
// in that coordinate direction.
// ============================================================

bool find_periodic_shift(
    const std::array<double, 3>& q,
    int& chosen_shift
)
{
    const double qmin =
        *std::min_element(
            q.begin(),
            q.end()
        );

    const double qmax =
        *std::max_element(
            q.begin(),
            q.end()
        );


    const double lower =
        (
            -TOL
            -
            qmin
        )
        /
        L;

    const double upper =
        (
            L
            +
            TOL
            -
            qmax
        )
        /
        L;


    const int kmin =
        static_cast<int>(
            std::ceil(
                lower
                -
                1.0e-12
            )
        );

    const int kmax =
        static_cast<int>(
            std::floor(
                upper
                +
                1.0e-12
            )
        );


    if (
        kmin
        >
        kmax
    )
    {
        return false;
    }


    const double centroid =
        (
            q[0]
            +
            q[1]
            +
            q[2]
        )
        /
        3.0;


    int preferred =
        -static_cast<int>(
            std::floor(
                centroid
                /
                L
            )
        );


    preferred =
        (std::max)(
            preferred,
            kmin
        );

    preferred =
        (std::min)(
            preferred,
            kmax
        );


    chosen_shift =
        preferred;


    return true;
}


// ============================================================
// Triangle diagnostics
// ============================================================

double distance3(
    const Point& a,
    const Point& b
)
{
    const double dx =
        CGAL::to_double(
            a.x()
            -
            b.x()
        );

    const double dy =
        CGAL::to_double(
            a.y()
            -
            b.y()
        );

    const double dz =
        CGAL::to_double(
            a.z()
            -
            b.z()
        );

    return std::sqrt(
        dx * dx
        +
        dy * dy
        +
        dz * dz
    );
}


// ============================================================
// Main
// ============================================================

int main(
    int argc,
    char** argv
)
{
    std::cout
        << std::setprecision(17);


    std::cout << std::endl;

    std::cout
        << "================================================"
        << std::endl;

    std::cout
        << "PERIODIC SURFACE MESHER"
        << std::endl;

    std::cout
        << "================================================"
        << std::endl;


    if (argc < 4)
    {
        std::cerr
            << "Usage:\n"
            << "periodic_surface_mesher.exe <cgal_case.txt> "
            << "<feature_file> <output_prefix> [facet_size_override_mm]\n";
        return 1;
    }

    const std::string config_file = argv[1];
    const std::string feature_file = argv[2];
    const std::string output_prefix = argv[3];

    RuntimeConfig runtime;
    if (!read_runtime_config(config_file, runtime))
    {
        std::cerr << "ERROR: could not read CGAL runtime config.\n";
        return 2;
    }

    L = runtime.L;
    try
    {
        SURFACE_EXPRESSION.parse(runtime.expression);
    }
    catch (const std::exception& e)
    {
        std::cerr << "ERROR: invalid surface expression: " << e.what() << "\n";
        return 2;
    }

    if (argc >= 5)
    {
        try { runtime.facet_size = std::stod(argv[4]); }
        catch (...) { std::cerr << "ERROR: invalid facet-size override.\n"; return 3; }
    }
    if (!std::isfinite(runtime.facet_size) || runtime.facet_size <= 0.0 || runtime.facet_size >= L)
    {
        std::cerr << "ERROR: facet_size out of range.\n";
        return 3;
    }

    std::cout << "config file       = " << config_file << std::endl;
    std::cout << "cell size L       = " << L << " mm" << std::endl;
    std::cout << "surface expression= " << runtime.expression << std::endl;
    std::cout << "facet_size        = " << runtime.facet_size << " mm" << std::endl;

    // --------------------------------------------------------
    // Read features
    // --------------------------------------------------------

    Polylines polylines;

    std::vector<FeatureMetadata>
        metadata;


    if (
        !read_features(
            feature_file,
            polylines,
            metadata
        )
    )
    {
        std::cerr
            << "ERROR: could not read feature file."
            << std::endl;

        return 2;
    }


    std::cout << std::endl;

    std::cout
        << "feature file     = "
        << feature_file
        << std::endl;

    std::cout
        << "input polylines  = "
        << polylines.size()
        << std::endl;


    std::size_t total_feature_points =
        0;


    for (
        const Polyline& p
        :
        polylines
    )
    {
        total_feature_points +=
            p.size();
    }


    std::cout
        << "feature points   = "
        << total_feature_points
        << std::endl;


    // --------------------------------------------------------
    // Build periodic implicit domain
    // --------------------------------------------------------

    const Iso_cuboid canonical_cube(
        0.0,
        0.0,
        0.0,
        L,
        L,
        L
    );


    Periodic_mesh_domain domain =
        Periodic_mesh_domain::
        create_implicit_mesh_domain(
            Periodic_function(
                surface_function,
                canonical_cube
            ),
            canonical_cube
        );


    // --------------------------------------------------------
    // Add ONLY the 8 master cut curves.
    //
    // X0 and XL are the same feature in the flat torus,
    // likewise Y0/YL and Z0/ZL.
    // --------------------------------------------------------

    domain.add_features(
        polylines.begin(),
        polylines.end()
    );


    // --------------------------------------------------------
    // Mesh criteria loaded from cgal_case.txt
    // --------------------------------------------------------
    const double EDGE_SIZE = runtime.edge_size;
    const double FACET_ANGLE = runtime.facet_angle;
    const double FACET_SIZE = runtime.facet_size;
    const double FACET_DISTANCE = runtime.facet_distance;
    const double CELL_RADIUS_EDGE_RATIO = runtime.cell_radius_edge_ratio;
    const double CELL_SIZE = runtime.cell_size;

    Periodic_mesh_criteria criteria(

        params::edge_size(
            EDGE_SIZE
        )

        .facet_angle(
            FACET_ANGLE
        )

        .facet_size(
            FACET_SIZE
        )

        .facet_distance(
            FACET_DISTANCE
        )

        .cell_radius_edge_ratio(
            CELL_RADIUS_EDGE_RATIO
        )

        .cell_size(
            CELL_SIZE
        )
    );


    std::cout << std::endl;

    std::cout
        << "Mesh criteria:"
        << std::endl;

    std::cout
        << "  edge_size              = "
        << EDGE_SIZE
        << std::endl;

    std::cout
        << "  facet_angle            = "
        << FACET_ANGLE
        << std::endl;

    std::cout
        << "  facet_size             = "
        << FACET_SIZE
        << std::endl;

    std::cout
        << "  facet_distance         = "
        << FACET_DISTANCE
        << std::endl;

    std::cout
        << "  cell_size              = "
        << CELL_SIZE
        << std::endl;


    // --------------------------------------------------------
    // Reproducibility
    // --------------------------------------------------------

    const unsigned int RANDOM_SEED = runtime.random_seed;

    CGAL::get_default_random() =
        CGAL::Random(
            RANDOM_SEED
        );

    std::cout << std::endl;

    std::cout
        << "CGAL random seed = "
        << RANDOM_SEED
        << std::endl;


    // --------------------------------------------------------
    // Generate periodic mesh.
    //
    // Important:
    //   features()
    //   manifold()
    //   no_perturb()
    //   no_exude()
    //
    // Keep mesh generation deterministic
    // with respect to post-refinement optimizers and prevent
    // optimization from altering the refinement result.
    // --------------------------------------------------------

    std::cout << std::endl;

    std::cout
        << "Generating feature-protected periodic mesh..."
        << std::endl;


    const auto t0 =
        std::chrono::steady_clock::now();


    C3t3 c3t3 =
        CGAL::make_periodic_3_mesh_3<
            C3t3
        >(
            domain,
            criteria,

            params::features()
                .manifold()
                .no_perturb()
                .no_exude()
        );


    const auto t1 =
        std::chrono::steady_clock::now();


    const double seconds =
        std::chrono::duration<double>(
            t1
            -
            t0
        ).count();


    const Tr& tr =
        c3t3.triangulation();


    std::cout << std::endl;

    std::cout
        << "Meshing completed."
        << std::endl;

    std::cout
        << "time = "
        << seconds
        << " s"
        << std::endl;


    // --------------------------------------------------------
    // Complex statistics
    // --------------------------------------------------------

    const auto n_vertices =
        tr.number_of_vertices();

    const auto n_surface_facets =
        c3t3.number_of_facets_in_complex();

    const auto n_cells =
        c3t3.number_of_cells_in_complex();

    const auto n_feature_edges =
        c3t3.number_of_edges();

    const auto n_corners =
        c3t3.number_of_corners();


    std::cout << std::endl;

    std::cout
        << "Mesh statistics:"
        << std::endl;

    std::cout
        << "  periodic vertices = "
        << n_vertices
        << std::endl;

    std::cout
        << "  surface facets    = "
        << n_surface_facets
        << std::endl;

    std::cout
        << "  domain cells      = "
        << n_cells
        << std::endl;

    std::cout
        << "  feature edges     = "
        << n_feature_edges
        << std::endl;

    std::cout
        << "  corners           = "
        << n_corners
        << std::endl;


    // --------------------------------------------------------
    // Canonical-cell placement test:
    //
    // For every surface triangle, CGAL's tr.triangle(facet)
    // reconstructs its actual Euclidean coordinates using
    // periodic offsets.
    //
    // Ask:
    //
    // Can all 3 vertices be moved into [0,L]^3 using ONE
    // integer cell translation?
    //
    // YES -> no geometric clipping required.
    // NO  -> triangle straddles a canonical cut and must be
    //        clipped or handled differently.
    // --------------------------------------------------------

    std::size_t facet_count =
        0;

    std::size_t facets_requiring_clipping =
        0;

    std::size_t facets_shifted =
        0;


    double max_unwrapped_edge =
        0.0;

    double max_axis_span =
        0.0;


    const std::string bad_csv =
        output_prefix
        +
        "_unplaceable_facets.csv";


    const std::string placed_csv =
        output_prefix
        +
        "_canonical_triangles.csv";


    std::ofstream placed(
        placed_csv
    );


    if (!placed)
    {
        std::cerr
            << "ERROR: cannot create canonical triangle CSV."
            << std::endl;

        return 5;
    }


    placed
        << std::setprecision(17);


    placed
        << "facet_id,"
        << "x0,y0,z0,"
        << "x1,y1,z1,"
        << "x2,y2,z2,"
        << "shift_x,shift_y,shift_z"
        << "\n";


    std::ofstream bad(
        bad_csv
    );


    bad
        << std::setprecision(17);

    bad
        << "facet_id,"
        << "x0,y0,z0,"
        << "x1,y1,z1,"
        << "x2,y2,z2,"
        << "x_placeable,"
        << "y_placeable,"
        << "z_placeable\n";


    for (
        auto fit =
            c3t3.facets_in_complex_begin();

        fit !=
            c3t3.facets_in_complex_end();

        ++fit
    )
    {
        const auto tri =
            tr.triangle(
                *fit
            );


        std::array<Point, 3> p = {
            tri.vertex(0),
            tri.vertex(1),
            tri.vertex(2)
        };


        std::array<double, 3> xs = {
            CGAL::to_double(
                p[0].x()
            ),
            CGAL::to_double(
                p[1].x()
            ),
            CGAL::to_double(
                p[2].x()
            )
        };


        std::array<double, 3> ys = {
            CGAL::to_double(
                p[0].y()
            ),
            CGAL::to_double(
                p[1].y()
            ),
            CGAL::to_double(
                p[2].y()
            )
        };


        std::array<double, 3> zs = {
            CGAL::to_double(
                p[0].z()
            ),
            CGAL::to_double(
                p[1].z()
            ),
            CGAL::to_double(
                p[2].z()
            )
        };


        int kx = 0;
        int ky = 0;
        int kz = 0;


        const bool ok_x =
            find_periodic_shift(
                xs,
                kx
            );

        const bool ok_y =
            find_periodic_shift(
                ys,
                ky
            );

        const bool ok_z =
            find_periodic_shift(
                zs,
                kz
            );


        const bool placeable =
            ok_x
            &&
            ok_y
            &&
            ok_z;


        if (!placeable)
        {
            ++facets_requiring_clipping;


            bad
                << facet_count;

            for (
                int i = 0;
                i < 3;
                ++i
            )
            {
                bad
                    << ","
                    << p[i].x()
                    << ","
                    << p[i].y()
                    << ","
                    << p[i].z();
            }

            bad
                << ","
                << static_cast<int>(
                    ok_x
                )

                << ","
                << static_cast<int>(
                    ok_y
                )

                << ","
                << static_cast<int>(
                    ok_z
                )

                << "\n";
        }
        else
        {
            if (
                kx != 0
                ||
                ky != 0
                ||
                kz != 0
            )
            {
                ++facets_shifted;
            }


            placed
                << facet_count;


            for (
                int i = 0;
                i < 3;
                ++i
            )
            {
                double qx =
                    xs[i]
                    +
                    static_cast<double>(kx)
                    * L;

                double qy =
                    ys[i]
                    +
                    static_cast<double>(ky)
                    * L;

                double qz =
                    zs[i]
                    +
                    static_cast<double>(kz)
                    * L;


                // --------------------------------------------
                // Snap ONLY numerical noise at canonical faces.
                // --------------------------------------------

                if (
                    std::abs(qx)
                    <=
                    TOL
                )
                {
                    qx = 0.0;
                }

                if (
                    std::abs(qx - L)
                    <=
                    TOL
                )
                {
                    qx = L;
                }


                if (
                    std::abs(qy)
                    <=
                    TOL
                )
                {
                    qy = 0.0;
                }

                if (
                    std::abs(qy - L)
                    <=
                    TOL
                )
                {
                    qy = L;
                }


                if (
                    std::abs(qz)
                    <=
                    TOL
                )
                {
                    qz = 0.0;
                }

                if (
                    std::abs(qz - L)
                    <=
                    TOL
                )
                {
                    qz = L;
                }


                // --------------------------------------------
                // No silent clamping.
                // --------------------------------------------

                if (
                    qx < -TOL
                    ||
                    qx > L + TOL
                    ||
                    qy < -TOL
                    ||
                    qy > L + TOL
                    ||
                    qz < -TOL
                    ||
                    qz > L + TOL
                )
                {
                    std::cerr
                        << "ERROR: placed facet lies outside "
                        << "canonical cell."
                        << std::endl;

                    return 6;
                }


                placed
                    << ","
                    << qx
                    << ","
                    << qy
                    << ","
                    << qz;
            }


            placed
                << ","
                << kx
                << ","
                << ky
                << ","
                << kz
                << "\n";
        }


        const double e01 =
            distance3(
                p[0],
                p[1]
            );

        const double e12 =
            distance3(
                p[1],
                p[2]
            );

        const double e20 =
            distance3(
                p[2],
                p[0]
            );


        max_unwrapped_edge =
            (std::max)({
                max_unwrapped_edge,
                e01,
                e12,
                e20
            });


        const double span_x =
            *std::max_element(
                xs.begin(),
                xs.end()
            )
            -
            *std::min_element(
                xs.begin(),
                xs.end()
            );


        const double span_y =
            *std::max_element(
                ys.begin(),
                ys.end()
            )
            -
            *std::min_element(
                ys.begin(),
                ys.end()
            );


        const double span_z =
            *std::max_element(
                zs.begin(),
                zs.end()
            )
            -
            *std::min_element(
                zs.begin(),
                zs.end()
            );


        max_axis_span =
            (std::max)({
                max_axis_span,
                span_x,
                span_y,
                span_z
            });


        ++facet_count;
    }


    bad.close();
    placed.close();


    std::cout << std::endl;

    std::cout
        << "================================================"
        << std::endl;

    std::cout
        << "CANONICAL-CELL CUT TEST"
        << std::endl;

    std::cout
        << "================================================"
        << std::endl;


    std::cout
        << "surface facets iterated  = "
        << facet_count
        << std::endl;

    std::cout
        << "facets shifted by period = "
        << facets_shifted
        << std::endl;

    std::cout
        << "facets requiring clipping= "
        << facets_requiring_clipping
        << std::endl;


    std::cout << std::endl;

    std::cout
        << "max physical surface edge = "
        << max_unwrapped_edge
        << std::endl;

    std::cout
        << "max triangle axis span     = "
        << max_axis_span
        << std::endl;


    // --------------------------------------------------------
    // Diagnostic visualization outputs
    // --------------------------------------------------------

    const std::string one_copy_file =
        output_prefix
        +
        "_1copy.mesh";

    const std::string eight_copy_file =
        output_prefix
        +
        "_8copy.mesh";


    {
        std::ofstream out(
            one_copy_file
        );

        CGAL::IO::
        output_periodic_mesh_to_medit(
            out,
            c3t3,
            1
        );
    }


    {
        std::ofstream out(
            eight_copy_file
        );

        CGAL::IO::
        output_periodic_mesh_to_medit(
            out,
            c3t3,
            8
        );
    }


    // --------------------------------------------------------
    // Acceptance
    // --------------------------------------------------------

    const bool pass =

        n_vertices
        >
        0

        &&

        n_surface_facets
        >
        0

        &&

        n_cells
        >
        0

        &&

        n_feature_edges
        >
        0

        &&

        n_corners
        >
        0

        &&

        facet_count
        ==
        n_surface_facets

        &&

        facets_requiring_clipping
        ==
        0;


    std::cout << std::endl;

    std::cout
        << "Saved:"
        << std::endl;

    std::cout
        << "  "
        << one_copy_file
        << std::endl;

    std::cout
        << "  "
        << eight_copy_file
        << std::endl;

    std::cout
        << "  "
        << bad_csv
        << std::endl;


    std::cout
        << "  "
        << placed_csv
        << std::endl;


    std::cout << std::endl;

    std::cout
        << "================================================"
        << std::endl;

    if (pass)
    {
        std::cout
            << "PERIODIC SURFACE MESHER STATUS: PASS"
            << std::endl;
    }
    else
    {
        std::cout
            << "PERIODIC SURFACE MESHER STATUS: FAIL"
            << std::endl;
    }

    std::cout
        << "================================================"
        << std::endl;


    return pass
        ? EXIT_SUCCESS
        : EXIT_FAILURE;
}
