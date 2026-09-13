#pragma once

// Small runtime expression evaluator used by the CGAL mesher.
// Supported syntax:
//   numbers, X/Y/Z, pi, + - * / ^, parentheses
//   sin(), cos(), tan(), exp(), sqrt(), abs()
// This keeps the surface equation in config/case.json instead of hard-coding
// a separate C++ copy for every case.

#include <cmath>
#include <cstdlib>
#include <cctype>
#include <stdexcept>
#include <string>
#include <vector>

class Expression {
public:
    Expression() = default;
    explicit Expression(const std::string& text) { parse(text); }

    void parse(const std::string& text) {
        text_ = text;
        pos_ = 0;
        root_ = parse_expression();
        skip_ws();
        if (pos_ != text_.size()) {
            throw std::runtime_error("Unexpected token near: " + text_.substr(pos_));
        }
    }

    double eval(double X, double Y, double Z) const {
        if (root_ < 0) throw std::runtime_error("Expression not initialized");
        return eval_node(root_, X, Y, Z);
    }

private:
    enum class Kind { Number, X, Y, Z, Add, Sub, Mul, Div, Pow, Neg,
                      Sin, Cos, Tan, Exp, Sqrt, Abs };
    struct Node {
        Kind kind;
        double value = 0.0;
        int a = -1;
        int b = -1;
    };

    std::string text_;
    std::size_t pos_ = 0;
    std::vector<Node> nodes_;
    int root_ = -1;

    void skip_ws() {
        while (pos_ < text_.size() && std::isspace(static_cast<unsigned char>(text_[pos_]))) ++pos_;
    }

    bool consume(char c) {
        skip_ws();
        if (pos_ < text_.size() && text_[pos_] == c) { ++pos_; return true; }
        return false;
    }

    int add(Node n) {
        nodes_.push_back(n);
        return static_cast<int>(nodes_.size()) - 1;
    }

    int parse_expression() {
        int lhs = parse_term();
        while (true) {
            if (consume('+')) lhs = add({Kind::Add, 0.0, lhs, parse_term()});
            else if (consume('-')) lhs = add({Kind::Sub, 0.0, lhs, parse_term()});
            else break;
        }
        return lhs;
    }

    int parse_term() {
        int lhs = parse_power();
        while (true) {
            if (consume('*')) lhs = add({Kind::Mul, 0.0, lhs, parse_power()});
            else if (consume('/')) lhs = add({Kind::Div, 0.0, lhs, parse_power()});
            else break;
        }
        return lhs;
    }

    int parse_power() {
        int lhs = parse_unary();
        if (consume('^')) {
            // Right-associative exponentiation.
            lhs = add({Kind::Pow, 0.0, lhs, parse_power()});
        }
        return lhs;
    }

    int parse_unary() {
        if (consume('+')) return parse_unary();
        if (consume('-')) return add({Kind::Neg, 0.0, parse_unary(), -1});
        return parse_primary();
    }

    std::string parse_identifier() {
        skip_ws();
        const std::size_t start = pos_;
        while (pos_ < text_.size()) {
            char c = text_[pos_];
            if (!std::isalnum(static_cast<unsigned char>(c)) && c != '_') break;
            ++pos_;
        }
        return text_.substr(start, pos_ - start);
    }

    int parse_primary() {
        skip_ws();
        if (consume('(')) {
            int n = parse_expression();
            if (!consume(')')) throw std::runtime_error("Missing ')' in expression");
            return n;
        }

        if (pos_ < text_.size() &&
            (std::isdigit(static_cast<unsigned char>(text_[pos_])) || text_[pos_] == '.')) {
            const char* begin = text_.c_str() + pos_;
            char* end = nullptr;
            double v = std::strtod(begin, &end);
            if (end == begin) throw std::runtime_error("Invalid number");
            pos_ += static_cast<std::size_t>(end - begin);
            return add({Kind::Number, v, -1, -1});
        }

        if (pos_ < text_.size() &&
            (std::isalpha(static_cast<unsigned char>(text_[pos_])) || text_[pos_] == '_')) {
            std::string id = parse_identifier();
            if (id == "X") return add({Kind::X});
            if (id == "Y") return add({Kind::Y});
            if (id == "Z") return add({Kind::Z});
            if (id == "pi" || id == "PI") return add({Kind::Number, 3.141592653589793238462643383279502884});

            Kind fn;
            if (id == "sin") fn = Kind::Sin;
            else if (id == "cos") fn = Kind::Cos;
            else if (id == "tan") fn = Kind::Tan;
            else if (id == "exp") fn = Kind::Exp;
            else if (id == "sqrt") fn = Kind::Sqrt;
            else if (id == "abs" || id == "Abs") fn = Kind::Abs;
            else throw std::runtime_error("Unknown identifier/function: " + id);

            if (!consume('(')) throw std::runtime_error("Function requires '(': " + id);
            int arg = parse_expression();
            if (!consume(')')) throw std::runtime_error("Function missing ')': " + id);
            return add({fn, 0.0, arg, -1});
        }

        throw std::runtime_error("Unexpected token in expression");
    }

    double eval_node(int i, double Xv, double Yv, double Zv) const {
        const Node& n = nodes_.at(static_cast<std::size_t>(i));
        switch (n.kind) {
            case Kind::Number: return n.value;
            case Kind::X: return Xv;
            case Kind::Y: return Yv;
            case Kind::Z: return Zv;
            case Kind::Add: return eval_node(n.a,Xv,Yv,Zv) + eval_node(n.b,Xv,Yv,Zv);
            case Kind::Sub: return eval_node(n.a,Xv,Yv,Zv) - eval_node(n.b,Xv,Yv,Zv);
            case Kind::Mul: return eval_node(n.a,Xv,Yv,Zv) * eval_node(n.b,Xv,Yv,Zv);
            case Kind::Div: return eval_node(n.a,Xv,Yv,Zv) / eval_node(n.b,Xv,Yv,Zv);
            case Kind::Pow: return std::pow(eval_node(n.a,Xv,Yv,Zv), eval_node(n.b,Xv,Yv,Zv));
            case Kind::Neg: return -eval_node(n.a,Xv,Yv,Zv);
            case Kind::Sin: return std::sin(eval_node(n.a,Xv,Yv,Zv));
            case Kind::Cos: return std::cos(eval_node(n.a,Xv,Yv,Zv));
            case Kind::Tan: return std::tan(eval_node(n.a,Xv,Yv,Zv));
            case Kind::Exp: return std::exp(eval_node(n.a,Xv,Yv,Zv));
            case Kind::Sqrt: return std::sqrt(eval_node(n.a,Xv,Yv,Zv));
            case Kind::Abs: return std::abs(eval_node(n.a,Xv,Yv,Zv));
        }
        throw std::runtime_error("Internal expression error");
    }
};
