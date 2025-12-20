from app import create_app

app = create_app()

if __name__ == '__main__':
    # debug=True geliştirme aşamasında hataları görmek için önemlidir
    app.run(debug=True)