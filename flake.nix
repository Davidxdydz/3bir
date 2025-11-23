{
  description = "threebir project flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        bir3 = pkgs.python312Packages.buildPythonApplication {
          pname = "bir3";
          version = "0.1.0";
          src = ./.;
          format = "pyproject";

          # Build dependencies
          nativeBuildInputs = [
            pkgs.makeWrapper
            pkgs.python312Packages.setuptools
            pkgs.python312Packages.wheel
          ];

          # Runtime dependencies
          propagatedBuildInputs = [
            pkgs.python312Packages.flask
            pkgs.python312Packages.flask-socketio
            pkgs.python312Packages.waitress
          ];

          # This is the magic step.
          # 1. We look for the 'waitress-serve' binary provided by the waitress package.
          # 2. We create a new binary in $out/bin named 'start-server'.
          # 3. We wrap it to execute waitress-serve with specific arguments.
          # 4. We add the current folder to PYTHONPATH so waitress can find 'app.py'
          postInstall = ''
            # Ensure site-packages exists (it should, but good practice)
            mkdir -p $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages

            mkdir -p $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages/static
            cp -r ${tailwindDeps}/static/css $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages/static

            # Copy templates directory if it exists
            if [ -d templates ]; then
              cp -r templates $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages/
            fi

            # Copy static directory if it exists
            if [ -d static ]; then
              cp -r static $out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages/
            fi
            makeWrapper ${pkgs.python312Packages.waitress}/bin/waitress-serve $out/bin/start-server \
                --prefix PYTHONPATH : "$out/lib/${pkgs.python312Packages.python.libPrefix}/site-packages:$PYTHONPATH" \
                --add-flags "--port=8080" \
                --add-flags "app:app"
          '';
        };
        tailwindDeps = pkgs.buildNpmPackage {
          pname = "bir3-npm-deps";
          version = "0.1.0";
          src = ./.; # Points to your project root where package.json lives

          # 1a. Configuration
          npmDepsHash = "sha256-5cnFZ7y94iZ5eqFKeCE8MPRB1gLgyi2ZJFHVxHM27Z4="; # Replace with actual hash!
          # Tip: Run `nix-build -E 'with import <nixpkgs> {}; buildNpmPackage { pname = "foo"; version = "1.0"; src = ./.; }'` to see the expected hash.
          buildPhase = ''
            echo "--- Running custom NPM script 'build:css' ---"
            npm run build:css
          '';

          # 1b. The Build Phase (Compiling CSS)
          installPhase = ''
            echo "--- Running Tailwind CSS Compilation ---"

            # The node_modules directory is already set up by buildNpmPackage

            # Run the Tailwind CLI using the local `node_modules/.bin`
            # We use $out/static as the destination for the final CSS file
            # ./node_modules/.bin/tailwindcss \
            #   -i ./src/input.css \
            #   -o $out/static/output.css \
            #   --minify

            # Ensure the static directory structure is created in $out
            mkdir -p $out/static
            cp -r static/css $out/static/

            # Check for the output file
            if [ ! -f $out/static/css/main.css ]; then
              echo "Tailwind compilation failed to produce main.css"
              exit 1
            fi
          '';
        };
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            (python312.withPackages (
              pp: with pp; [
                flask
                flask-socketio
                build
                waitress
              ]
            ))
            pyright
            bir3
            nodejs
          ];
        };
        packages = {
          default = bir3;
          inherit tailwindDeps;
          dockerImage = pkgs.dockerTools.streamLayeredImage {
            name = "3bir";
            tag = "latest";
            contents = [ bir3 ];
            config = {
              Cmd = [ "${bir3}/bin/start-server" ];
              ExposedPorts = {
                "8080/tcp" = { };
              };
            };
          };
        };

        apps.default = {
          type = "app";
          program = "${bir3}/bin/start-server";
        };
      }
    );
}
